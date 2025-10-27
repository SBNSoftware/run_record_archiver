import logging
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List
from .clients.artdaq import ArtdaqDBClient
from .config import Config
from .exceptions import ArchiverError, FuzzSkipError
from .persistence import state
from .services.fcl_preparer import FclPreparer
from .services.reporting import send_failure_report

class Importer:

    def __init__(self, config: Config, artdaq_client: ArtdaqDBClient):
        self._config = config
        self._artdaq = artdaq_client
        self._fcl_preparer = FclPreparer(fcl_conf_dir=self._config.artdaq_db.fcl_conf_dir, fhiclize_config=self._config.fhiclize_generate)
        self._logger = logging.getLogger(__name__)
        self._shutdown_check = lambda : False

    def set_shutdown_check(self, shutdown_check_func):
        self._shutdown_check = shutdown_check_func

    def _get_candidate_runs(self, incremental: bool) -> List[int]:
        self._logger.info('Import Stage: Fetching runs (mode: %s).', 'incremental' if incremental else 'full')
        self._logger.debug('Reading run records from: %s', self._config.source_files.run_records_dir)
        try:
            fs_runs = {int(p.name) for p in self._config.source_files.run_records_dir.iterdir() if p.is_dir() and p.name.isdigit()}
            self._logger.info('Found %d run directories in filesystem', len(fs_runs))
        except (IOError, PermissionError) as e:
            raise ArchiverError(f'Cannot read run records directory: {e}', stage='Import', context={'directory': str(self._config.source_files.run_records_dir)}) from e
        self._logger.info('Querying ArtdaqDB for already archived runs...')
        artdaq_runs = self._artdaq.get_archived_runs()
        self._logger.info('Found %d runs already in ArtdaqDB', len(artdaq_runs))
        candidate_runs = sorted(list(fs_runs - artdaq_runs))
        self._logger.debug('Candidate runs before filtering: %s', candidate_runs[:10] if len(candidate_runs) > 10 else candidate_runs)
        if incremental:
            last_run = state.get_incremental_start_run(self._config.app.import_state_file)
            self._logger.info('Incremental mode: filtering runs > %d', last_run)
            candidate_runs = [r for r in candidate_runs if r > last_run]
        self._logger.info('Import Stage: Found %d runs to import.', len(candidate_runs))
        if candidate_runs:
            self._logger.info('Run range: %d to %d', min(candidate_runs), max(candidate_runs))
        return candidate_runs

    def _process_run(self, run_number: int) -> bool:
        retries = self._config.app.run_process_retries
        for attempt in range(retries + 1):
            try:
                self._logger.info('→ Processing run %d (attempt %d/%d)', run_number, attempt + 1, retries + 1)
                run_dir = self._config.source_files.run_records_dir / str(run_number)
                if not run_dir.is_dir():
                    self._logger.error('Run directory not found: %s', run_dir)
                    raise ArchiverError(f'Run directory not found', stage='Import', run_number=run_number, context={'directory': str(run_dir)})
                with tempfile.TemporaryDirectory(prefix=f'importer_{run_number}_') as tmpdir:
                    tmpdir_path = Path(tmpdir)
                    self._logger.debug('Run %d: Preparing FHiCL files for archive', run_number)
                    config_name = self._fcl_preparer.prepare_fcl_for_archive(run_dir, tmpdir_path)
                    self._logger.debug('Run %d: Archiving to ArtdaqDB (initial insert)', run_number)
                    self._artdaq.archive_run(run_number, config_name, tmpdir_path, update=False)
                    shutil.rmtree(tmpdir_path)
                    tmpdir_path.mkdir()
                    self._logger.debug('Run %d: Preparing FHiCL files for update', run_number)
                    has_update = self._fcl_preparer.prepare_fcl_for_update(run_dir, tmpdir_path)
                    if has_update:
                        self._logger.debug('Run %d: Updating ArtdaqDB with stop-time', run_number)
                        self._artdaq.archive_run(run_number, config_name, tmpdir_path, update=True)
                    else:
                        self._logger.debug('Run %d: No stop-time available, skipping update', run_number)
                self._logger.info('✓ Run %d imported successfully', run_number)
                return True
            except FuzzSkipError as e:
                self._logger.error('✗ Run %d permanently failed (fuzz skip): %s', run_number, e)
                return False
            except ArchiverError as e:
                self._logger.error('✗ Run %d failed (attempt %d/%d): %s', run_number, attempt + 1, retries + 1, e)
                if attempt < retries:
                    self._logger.info('Retrying run %d in %d seconds...', run_number, self._config.app.retry_delay_seconds)
                    time.sleep(self._config.app.retry_delay_seconds)
        return False

    def _process_batch(self, runs_to_process: List[int]) -> tuple[List[int], List[int]]:
        (successful, failed) = ([], [])
        total = len(runs_to_process)
        max_workers = self._config.app.parallel_workers if self._artdaq.use_tools else 1
        self._logger.info('Starting parallel processing of %d runs with %d workers', total, max_workers)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(self._process_run, run): run for run in runs_to_process}
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
                    self._logger.exception('Import Stage: Run %d failed with unhandled error: %s', run, e)
                    failed.append(run)
                if completed_count % 10 == 0 or completed_count == total:
                    self._logger.info('Progress: %d/%d runs processed (%d successful, %d failed)', completed_count, total, len(successful), len(failed))
                if self._shutdown_check():
                    shutdown_triggered = True
                    cancelled_count = 0
                    for pending_future in future_map.keys():
                        if not pending_future.done():
                            if pending_future.cancel():
                                cancelled_count += 1
                    remaining = total - completed_count
                    if remaining > 0:
                        self._logger.warning('Shutdown requested - cancelled %d pending runs. %d runs in progress will complete.', cancelled_count, remaining - cancelled_count)
                    if remaining - cancelled_count > 0:
                        self._logger.info('Waiting for %d in-progress runs to complete...', remaining - cancelled_count)
                        for pending_future in future_map.keys():
                            if not pending_future.done() and (not pending_future.cancelled()):
                                pending_run = future_map[pending_future]
                                try:
                                    if pending_future.result():
                                        successful.append(pending_run)
                                    else:
                                        failed.append(pending_run)
                                except Exception as e:
                                    self._logger.exception('Import Stage: Run %d failed during shutdown: %s', pending_run, e)
                                    failed.append(pending_run)
                    break
            if shutdown_triggered:
                cancelled_runs = [future_map[f] for f in future_map.keys() if f.cancelled()]
                if cancelled_runs:
                    self._logger.info('Marking %d cancelled runs as not processed', len(cancelled_runs))
        if shutdown_triggered:
            self._logger.info('Batch processing interrupted by shutdown: %d successful, %d failed, %d not processed', len(successful), len(failed), total - len(successful) - len(failed))
        else:
            self._logger.info('Batch processing complete: %d successful, %d failed', len(successful), len(failed))
        if failed:
            self._logger.warning('Recording %d failed runs to failure log', len(failed))
            state.append_to_failure_log(self._config.app.import_failure_log, failed)
            send_failure_report(failed, self._config.reporting, 'import')
        return (successful, failed)

    def run(self, incremental: bool, import_only: bool=False) -> int:
        try:
            runs = self._get_candidate_runs(incremental)
        except ArchiverError as e:
            self._logger.critical('Import Stage: Failed to determine runs to import: %s', e)
            return 1
        if not runs:
            self._logger.info('Import Stage: No new runs to import.')
            return 0
        max_runs = self._config.app.batch_size if incremental else self._config.app.batch_size * 10
        batch = runs[:max_runs]
        if len(runs) > max_runs:
            mode_desc = 'batch_size' if incremental else 'batch_size * 10'
            self._logger.info('Import Stage: Limited to %d runs (%s). %d runs remaining.', max_runs, mode_desc, len(runs) - max_runs)
        self._logger.info('Import Stage: Processing batch of %d runs.', len(batch))
        (successful, failed) = self._process_batch(batch)
        attempted_runs = successful + failed
        self._logger.info('Updating state tracking: %d successful, %d attempted', len(successful), len(attempted_runs))
        state.update_contiguous_run_state(self._config.app.import_state_file, successful)
        state.update_attempted_run_state(self._config.app.import_state_file, attempted_runs)
        if self._shutdown_check():
            self._logger.info('Import Stage: Shutdown requested - state saved, exiting gracefully')
            return 1
        return 1 if len(successful) < len(batch) else 0

    def run_failure_recovery(self) -> int:
        failure_log = self._config.app.import_failure_log
        if not failure_log.is_file():
            self._logger.info('Import Stage: No failure log found. Nothing to recover.')
            return 0
        failed_runs = state.parse_run_records_from_file(failure_log)
        if not failed_runs:
            self._logger.info('Import Stage: Failure log is empty.')
            return 0
        self._logger.debug('Querying ArtdaqDB to filter already-archived runs...')
        archived_runs = self._artdaq.get_archived_runs()
        already_archived = sorted(list(set(failed_runs) & archived_runs))
        runs_to_retry = sorted(list(set(failed_runs) - archived_runs))
        if already_archived:
            self._logger.info('Found %d run(s) already archived, removing from failure log: %s', len(already_archived), already_archived[:10] if len(already_archived) > 10 else already_archived)
        if not runs_to_retry:
            self._logger.info('All failed runs are already archived. Nothing to retry.')
            state.write_failure_log(failure_log, [])
            return 0
        self._logger.info('Import Stage: Attempting to recover %d failed runs.', len(runs_to_retry))
        (successful, failed) = self._process_batch(runs_to_retry)
        all_successful = sorted(list(set(successful) | set(already_archived)))
        remaining_failures = sorted(list(set(failed_runs) - set(all_successful)))
        state.write_failure_log(failure_log, remaining_failures)
        attempted_runs = successful + failed
        self._logger.info('Updating state tracking after recovery: %d newly imported, %d total attempted in recovery', len(successful), len(attempted_runs))
        self._logger.debug('Querying all archived runs for state update...')
        all_archived = self._artdaq.get_archived_runs()
        state.update_contiguous_run_state(self._config.app.import_state_file, sorted(list(all_archived)))
        state.update_attempted_run_state(self._config.app.import_state_file, attempted_runs)
        if self._shutdown_check():
            self._logger.info('Import Recovery: Shutdown requested - state saved, exiting gracefully')
            return 1
        self._logger.info('Import Stage: Recovery complete. %d successful (%d already archived, %d newly imported), %d remaining.', len(all_successful), len(already_archived), len(successful), len(remaining_failures))
        return 1 if remaining_failures else 0