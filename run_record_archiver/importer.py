import logging
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List

from .clients.artdaq import ArtdaqDBClient
from .config import Config
from .exceptions import ArchiverError
from .persistence import state
from .services.fcl_preparer import FclPreparer
from .services.reporting import send_failure_report


class Importer:
    def __init__(self, config: Config, artdaq_client: ArtdaqDBClient):
        self._config = config
        self._artdaq = artdaq_client
        self._fcl_preparer = FclPreparer(
            fcl_conf_dir=self._config.artdaq_db.fcl_conf_dir
        )
        self._logger = logging.getLogger(__name__)

    def _get_candidate_runs(self, incremental: bool) -> List[int]:
        self._logger.info(
            "Import Stage: Fetching runs (mode: %s).",
            "incremental" if incremental else "full",
        )
        try:
            fs_runs = {
                int(p.name)
                for p in self._config.source_files.run_records_dir.iterdir()
                if p.is_dir() and p.name.isdigit()
            }
        except (IOError, PermissionError) as e:
            raise ArchiverError(f"Cannot read run records directory: {e}") from e

        artdaq_runs = self._artdaq.get_archived_runs()
        candidate_runs = sorted(list(fs_runs - artdaq_runs))

        if incremental:
            last_run = state.read_state(self._config.app.import_state_file).get(
                "last_contiguous_run", 0
            )
            candidate_runs = [r for r in candidate_runs if r > last_run]

        self._logger.info(
            "Import Stage: Found %d runs to import.", len(candidate_runs)
        )
        return candidate_runs

    def _process_run(self, run_number: int) -> bool:
        retries = self._config.app.run_process_retries
        for attempt in range(retries + 1):
            try:
                self._logger.info(
                    "Import Stage: Processing run %d (attempt %d)",
                    run_number,
                    attempt + 1,
                )
                run_dir = self._config.source_files.run_records_dir / str(run_number)
                if not run_dir.is_dir():
                    self._logger.error("Run directory not found: %s", run_dir)
                    return False

                with tempfile.TemporaryDirectory(
                    prefix=f"importer_{run_number}_"
                ) as tmpdir:
                    tmpdir_path = Path(tmpdir)
                    config_name = self._fcl_preparer.prepare_fcl_for_archive(
                        run_dir, tmpdir_path
                    )
                    self._artdaq.archive_run(
                        run_number, config_name, tmpdir_path, update=False
                    )
                    shutil.rmtree(tmpdir_path)
                    tmpdir_path.mkdir()
                    self._fcl_preparer.prepare_fcl_for_update(run_dir, tmpdir_path)
                    self._artdaq.archive_run(
                        run_number, config_name, tmpdir_path, update=True
                    )
                self._logger.info(
                    "Import Stage: Successfully imported run %d.", run_number
                )
                return True
            except ArchiverError as e:
                self._logger.error(
                    "Import Stage: Failed to process run %d (attempt %d/%d): %s",
                    run_number,
                    attempt + 1,
                    retries + 1,
                    e,
                )
                if attempt < retries:
                    time.sleep(self._config.app.retry_delay_seconds)
        return False

    def _process_batch(self, runs_to_process: List[int]) -> List[int]:
        successful, failed = [], []
        with ThreadPoolExecutor(
            max_workers=self._config.app.parallel_workers
        ) as executor:
            future_map = {
                executor.submit(self._process_run, run): run for run in runs_to_process
            }
            for future in as_completed(future_map):
                run = future_map[future]
                try:
                    if future.result():
                        successful.append(run)
                    else:
                        failed.append(run)
                except Exception:
                    self._logger.exception(
                        "Import Stage: Run %d failed with unhandled error", run
                    )
                    failed.append(run)

        if failed:
            state.append_to_failure_log(self._config.app.import_failure_log, failed)
            send_failure_report(failed, self._config.reporting, "import")
        return successful

    def run(self, incremental: bool) -> int:
        try:
            runs = self._get_candidate_runs(incremental)
        except ArchiverError as e:
            self._logger.critical("Import Stage: Failed to determine runs to import: %s", e)
            return 1

        if not runs:
            self._logger.info("Import Stage: No new runs to import.")
            return 0

        batch = runs[: self._config.app.batch_size]
        self._logger.info("Import Stage: Processing batch of %d runs.", len(batch))
        successful = self._process_batch(batch)

        if incremental:
            state.update_contiguous_run_state(
                self._config.app.import_state_file, successful
            )

        return 1 if len(successful) < len(batch) else 0

    def run_failure_recovery(self) -> int:
        failure_log = self._config.app.import_failure_log
        if not failure_log.is_file():
            self._logger.info("Import Stage: No failure log found. Nothing to recover.")
            return 0

        failed_runs = state.parse_run_records_from_file(failure_log)
        if not failed_runs:
            self._logger.info("Import Stage: Failure log is empty.")
            return 0

        self._logger.info(
            "Import Stage: Attempting to recover %d failed runs.", len(failed_runs)
        )
        successful = self._process_batch(failed_runs)
        remaining_failures = sorted(list(set(failed_runs) - set(successful)))
        state.write_failure_log(failure_log, remaining_failures)
        self._logger.info(
            "Import Stage: Recovery complete. %d successful, %d remaining.",
            len(successful),
            len(remaining_failures),
        )
        return 1 if remaining_failures else 0
