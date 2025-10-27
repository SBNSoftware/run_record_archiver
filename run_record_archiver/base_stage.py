import logging
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, List
from .config import Config
from .constants import PROGRESS_REPORT_INTERVAL
from .enums import Stage
from .exceptions import ArchiverError, FuzzSkipError
from .persistence import state
from .services.reporting import send_failure_report

class BaseStage(ABC):

    def __init__(self, config: Config):
        self._config = config
        self._logger = logging.getLogger(self.__class__.__name__)
        self._shutdown_check: Callable[[], bool] = lambda : False

    def set_shutdown_check(self, shutdown_check_func: Callable[[], bool]) -> None:
        self._shutdown_check = shutdown_check_func

    @abstractmethod
    def _get_work_items(self, incremental: bool) -> List[int]:
        pass

    @abstractmethod
    def _process_single_item(self, run_number: int) -> bool:
        pass

    @abstractmethod
    def _get_state_file_path(self) -> Path:
        pass

    @abstractmethod
    def _get_failure_log_path(self) -> Path:
        pass

    @abstractmethod
    def _get_stage_name(self) -> str:
        pass

    def _get_max_workers(self) -> int:
        return self._config.app.parallel_workers

    def _process_run_with_retry(self, run_number: int) -> bool:
        retries = self._config.app.run_process_retries
        stage_name = self._get_stage_name()
        for attempt in range(retries + 1):
            try:
                self._logger.info('→ Processing run %d (attempt %d/%d)', run_number, attempt + 1, retries + 1)
                if self._process_single_item(run_number):
                    self._logger.info('✓ Run %d processed successfully', run_number)
                    return True
                else:
                    self._logger.error('✗ Run %d processing failed', run_number)
                    return False
            except FuzzSkipError as e:
                self._logger.error('✗ Run %d permanently failed (fuzz skip): %s', run_number, e)
                return False
            except ArchiverError as e:
                self._logger.error('✗ Run %d failed (attempt %d/%d): %s', run_number, attempt + 1, retries + 1, e)
                if attempt < retries:
                    delay = self._config.app.retry_delay_seconds
                    self._logger.info('Retrying run %d in %d seconds...', run_number, delay)
                    time.sleep(delay)
        return False

    def _process_batch(self, runs_to_process: List[int]) -> List[int]:
        successful: List[int] = []
        failed: List[int] = []
        total = len(runs_to_process)
        max_workers = self._get_max_workers()
        stage_name = self._get_stage_name()
        self._logger.info('Starting parallel processing of %d runs with %d workers', total, max_workers)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(self._process_run_with_retry, run): run for run in runs_to_process}
            completed_count = 0
            shutdown_triggered = False
            for future in as_completed(future_map):
                run = future_map[future]
                completed_count += 1
                try:
                    if future.result():
                        successful.append(run)
                    else:
                        failed.append(run)
                except Exception as e:
                    self._logger.exception('%s Stage: Run %d failed with unhandled error: %s', stage_name, run, e)
                    failed.append(run)
                if completed_count % PROGRESS_REPORT_INTERVAL == 0 or completed_count == total:
                    self._logger.info('Progress: %d/%d runs processed (%d successful, %d failed)', completed_count, total, len(successful), len(failed))
                if self._shutdown_check():
                    shutdown_triggered = True
                    self._handle_shutdown(executor, future_map, successful, failed, total, completed_count)
                    break
        if shutdown_triggered:
            self._logger.info('Batch processing interrupted by shutdown: %d successful, %d failed, %d not processed', len(successful), len(failed), total - len(successful) - len(failed))
        else:
            self._logger.info('Batch processing complete: %d successful, %d failed', len(successful), len(failed))
        if failed:
            self._logger.warning('Recording %d failed runs to failure log', len(failed))
            state.append_to_failure_log(self._get_failure_log_path(), failed)
            send_failure_report(failed, self._config.reporting, self._get_stage_name().lower())
        return successful

    def _handle_shutdown(self, executor: ThreadPoolExecutor, future_map: dict, successful: List[int], failed: List[int], total: int, completed_count: int) -> None:
        cancelled_count = 0
        for future in future_map.keys():
            if not future.done():
                if future.cancel():
                    cancelled_count += 1
        remaining = total - completed_count
        if remaining > 0:
            self._logger.warning('Shutdown requested - cancelled %d pending runs. %d runs in progress will complete.', cancelled_count, remaining - cancelled_count)
        in_progress_count = remaining - cancelled_count
        if in_progress_count > 0:
            self._logger.info('Waiting for %d in-progress runs to complete...', in_progress_count)
            for (future, run) in future_map.items():
                if not future.done() and (not future.cancelled()):
                    try:
                        if future.result():
                            successful.append(run)
                        else:
                            failed.append(run)
                    except Exception as e:
                        self._logger.exception('%s Stage: Run %d failed during shutdown: %s', self._get_stage_name(), run, e)
                        failed.append(run)

    def run(self, incremental: bool=False) -> int:
        stage_name = self._get_stage_name()
        try:
            runs = self._get_work_items(incremental)
        except ArchiverError as e:
            self._logger.critical('%s Stage: Failed to determine runs to process: %s', stage_name, e)
            return 1
        if not runs:
            self._logger.info('%s Stage: No runs to process.', stage_name)
            return 0
        successful = self._process_batch(runs)
        if successful:
            state.update_contiguous_run_state(self._get_state_file_path(), successful)
        return 0

    def run_failure_recovery(self) -> int:
        stage_name = self._get_stage_name()
        failure_log = self._get_failure_log_path()
        failed_runs = state.read_failure_log(failure_log)
        if not failed_runs:
            self._logger.info('%s Stage: No failed runs to retry.', stage_name)
            return 0
        self._logger.info('%s Stage: Retrying %d failed runs from %s', stage_name, len(failed_runs), failure_log)
        state.clear_failure_log(failure_log)
        successful = self._process_batch(failed_runs)
        if successful:
            state.update_contiguous_run_state(self._get_state_file_path(), successful)
        return 0