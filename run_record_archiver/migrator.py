import hashlib
import logging
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional
import requests
import urllib3
from .clients.artdaq import ArtdaqDBClient
from .clients.carbon import CarbonClient
from .clients.ucondb import UconDBClient
from .config import Config
from .exceptions import ArchiverError, VerificationError, FuzzSkipError
from .persistence import state
from .services.blob_creator import BlobCreator
from .services.blob_validator import BlobValidator
from .services.reporting import send_failure_report

class Migrator:

    def __init__(self, config: Config, artdaq_client: ArtdaqDBClient, ucon_client: UconDBClient, blob_creator: BlobCreator, carbon_client: Optional[CarbonClient]=None):
        self._config = config
        self._artdaq = artdaq_client
        self._ucon = ucon_client
        self._blob_creator = blob_creator
        self._blob_validator = BlobValidator()
        self._carbon_client = carbon_client
        self._logger = logging.getLogger(__name__)
        self._shutdown_check = lambda : False
        self._validate_blobs = False
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def set_shutdown_check(self, shutdown_check_func):
        self._shutdown_check = shutdown_check_func

    def _get_runs_to_migrate(self, incremental: bool) -> List[int]:
        self._logger.info('Migration Stage: Fetching runs (mode: %s).', 'incremental' if incremental else 'full')
        self._logger.info('Querying ArtdaqDB for available runs...')
        artdaq_runs = self._artdaq.get_archived_runs()
        self._logger.info('Found %d runs in ArtdaqDB', len(artdaq_runs))
        self._logger.info('Querying UconDB for already migrated runs...')
        ucon_runs = self._ucon.get_existing_runs()
        self._logger.info('Found %d runs already in UconDB', len(ucon_runs))
        runs_to_migrate = sorted(list(artdaq_runs - ucon_runs))
        self._logger.debug('Candidate runs before filtering: %s', runs_to_migrate[:10] if len(runs_to_migrate) > 10 else runs_to_migrate)
        if incremental:
            last_success = state.get_incremental_start_run(self._config.app.migrate_state_file)
            self._logger.info('Incremental mode: filtering runs > %d', last_success)
            runs_to_migrate = [run for run in runs_to_migrate if run > last_success]
        self._logger.info('Migration Stage: Found %d runs to migrate.', len(runs_to_migrate))
        if runs_to_migrate:
            self._logger.info('Run range: %d to %d', min(runs_to_migrate), max(runs_to_migrate))
        return runs_to_migrate

    def _get_ucondb_data_url(self, run_number: int) -> str:
        base_url = self._config.ucon_db.server_url
        folder = self._config.ucon_db.folder_name
        obj = self._config.ucon_db.object_name
        return f'{base_url}/data/{folder}/{obj}/key={run_number}'

    def _process_run(self, run_number: int) -> bool:
        retries = self._config.app.run_process_retries
        for attempt in range(retries + 1):
            try:
                self._logger.info('→ Processing run %d (attempt %d/%d)', run_number, attempt + 1, retries + 1)
                with tempfile.TemporaryDirectory(prefix=f'migrator_{run_number}_') as tmpdir:
                    tmpdir_path = Path(tmpdir)
                    self._logger.debug('Run %d: Exporting from ArtdaqDB', run_number)
                    self._artdaq.export_run_configuration(run_number, tmpdir_path)
                    self._logger.debug('Run %d: Creating data blob', run_number)
                    generated_blob = self._blob_creator.create_blob_from_directory(run_number, tmpdir_path)
                    blob_size = len(generated_blob)
                    self._logger.debug('Run %d: Generated blob size: %d bytes', run_number, blob_size)
                    self._logger.debug('Run %d: Uploading to UconDB', run_number)
                    self._ucon.upload_blob(run_number, generated_blob)
                    self._logger.debug('Run %d: Upload successful', run_number)
                    data_url = self._get_ucondb_data_url(run_number)
                    self._logger.debug('Run %d: Verifying integrity from UconDB', run_number)
                    response = requests.get(data_url, verify=False, timeout=30)
                    response.raise_for_status()
                    downloaded_blob = response.text
                    h1 = hashlib.md5(generated_blob.encode('utf-8')).hexdigest()
                    h2 = hashlib.md5(downloaded_blob.encode('utf-8')).hexdigest()
                    if h1 != h2:
                        raise VerificationError(f'MD5 mismatch between generated and downloaded blobs', stage='Migration', run_number=run_number, context={'generated_md5': h1, 'downloaded_md5': h2})
                    self._logger.debug('Run %d: MD5 verification passed (hash: %s)', run_number, h1)
                    if self._validate_blobs:
                        self._logger.debug('Run %d: Validating blob metadata', run_number)
                        (error_count, results) = self._blob_validator.validate_blob(downloaded_blob, run_number)
                        if error_count > 0:
                            self._logger.warning('Run %d: Blob validation found %d errors: %s', run_number, error_count, results)
                        else:
                            self._logger.debug('Run %d: Blob validation passed: %s', run_number, results)
                self._logger.info('✓ Run %d migrated and verified successfully', run_number)
                return True
            except FuzzSkipError as e:
                self._logger.error('✗ Run %d permanently failed (fuzz skip): %s', run_number, e)
                return False
            except (ArchiverError, requests.RequestException) as e:
                self._logger.error('✗ Run %d failed (attempt %d/%d): %s', run_number, attempt + 1, retries + 1, e)
                if attempt < retries:
                    self._logger.info('Retrying run %d in %d seconds...', run_number, self._config.app.retry_delay_seconds)
                    time.sleep(self._config.app.retry_delay_seconds)
        return False

    def _process_batch(self, runs: List[int]) -> tuple[List[int], List[int]]:
        (successful, failed) = ([], [])
        total = len(runs)
        max_workers = self._config.app.parallel_workers if self._artdaq.use_tools else 1
        self._logger.info('Starting parallel processing of %d runs with %d workers', total, max_workers)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_run = {executor.submit(self._process_run, run): run for run in runs}
            completed_count = 0
            shutdown_triggered = False
            for future in as_completed(future_to_run):
                run = future_to_run[future]
                completed_count += 1
                try:
                    if future.result():
                        successful.append(run)
                    else:
                        failed.append(run)
                except Exception as e:
                    self._logger.exception('Migration Stage: Run %d failed with unhandled exception: %s', run, e)
                    failed.append(run)
                if completed_count % 10 == 0 or completed_count == total:
                    self._logger.info('Progress: %d/%d runs processed (%d successful, %d failed)', completed_count, total, len(successful), len(failed))
                if self._shutdown_check():
                    shutdown_triggered = True
                    cancelled_count = 0
                    for pending_future in future_to_run.keys():
                        if not pending_future.done():
                            if pending_future.cancel():
                                cancelled_count += 1
                    remaining = total - completed_count
                    if remaining > 0:
                        self._logger.warning('Shutdown requested - cancelled %d pending runs. %d runs in progress will complete.', cancelled_count, remaining - cancelled_count)
                    if remaining - cancelled_count > 0:
                        self._logger.info('Waiting for %d in-progress runs to complete...', remaining - cancelled_count)
                        for pending_future in future_to_run.keys():
                            if not pending_future.done() and (not pending_future.cancelled()):
                                pending_run = future_to_run[pending_future]
                                try:
                                    if pending_future.result():
                                        successful.append(pending_run)
                                    else:
                                        failed.append(pending_run)
                                except Exception as e:
                                    self._logger.exception('Migration Stage: Run %d failed during shutdown: %s', pending_run, e)
                                    failed.append(pending_run)
                    break
            if shutdown_triggered:
                cancelled_runs = [future_to_run[f] for f in future_to_run.keys() if f.cancelled()]
                if cancelled_runs:
                    self._logger.info('Marking %d cancelled runs as not processed', len(cancelled_runs))
        if shutdown_triggered:
            self._logger.info('Batch processing interrupted by shutdown: %d successful, %d failed, %d not processed', len(successful), len(failed), total - len(successful) - len(failed))
        else:
            self._logger.info('Batch processing complete: %d successful, %d failed', len(successful), len(failed))
        if failed:
            self._logger.warning('Recording %d failed runs to failure log', len(failed))
            state.append_to_failure_log(self._config.app.migrate_failure_log, failed)
            send_failure_report(failed, self._config.reporting, 'migration')
        return (successful, failed)

    def _update_metrics(self, processed: int, successful: int, max_run: Optional[int]) -> None:
        if self._carbon_client and self._carbon_client.enabled:
            self._carbon_client.post_metric('migrate.runs_processed', processed)
            self._carbon_client.post_metric('migrate.runs_successful', successful)
            self._carbon_client.post_metric('migrate.runs_failed', processed - successful)
            if max_run is not None:
                self._carbon_client.post_metric('migrate.last_successful_run', max_run)

    def run(self, incremental: bool, migrate_only: bool=False, validate: bool=False) -> int:
        self._validate_blobs = validate
        if validate:
            self._logger.info('Migration Stage: Blob validation enabled')
        try:
            runs = self._get_runs_to_migrate(incremental)
        except ArchiverError as e:
            self._logger.critical('Migration Stage: Failed to determine runs to migrate: %s', e)
            return 1
        if not runs:
            self._logger.info('Migration Stage: No new runs to migrate.')
            self._update_metrics(0, 0, None)
            return 0
        max_runs = self._config.app.batch_size if incremental else self._config.app.batch_size * 10
        batch = runs[:max_runs]
        if len(runs) > max_runs:
            mode_desc = 'batch_size' if incremental else 'batch_size * 10'
            self._logger.info('Migration Stage: Limited to %d runs (%s). %d runs remaining.', max_runs, mode_desc, len(runs) - max_runs)
        self._logger.info('Migration Stage: Processing batch of %d runs.', len(batch))
        (successful, failed) = self._process_batch(batch)
        max_success = max(successful) if successful else None
        attempted_runs = successful + failed
        self._update_metrics(len(attempted_runs), len(successful), max_success)
        self._logger.info('Updating state tracking: %d successful, %d attempted', len(successful), len(attempted_runs))
        state.update_contiguous_run_state(self._config.app.migrate_state_file, successful)
        state.update_attempted_run_state(self._config.app.migrate_state_file, attempted_runs)
        if self._shutdown_check():
            self._logger.info('Migration Stage: Shutdown requested - state saved, exiting gracefully')
            return 1
        return 1 if len(successful) < len(batch) else 0

    def run_failure_recovery(self) -> int:
        failure_log = self._config.app.migrate_failure_log
        if not failure_log.exists():
            self._logger.info('Migration Stage: No failure log, nothing to recover.')
            return 0
        failed_runs = state.parse_run_records_from_file(failure_log)
        if not failed_runs:
            self._logger.info('Migration Stage: No failed runs in log to recover.')
            return 0
        self._logger.debug('Querying UconDB to filter already-migrated runs...')
        migrated_runs = self._ucon.get_existing_runs()
        already_migrated = sorted(list(set(failed_runs) & migrated_runs))
        runs_to_retry = sorted(list(set(failed_runs) - migrated_runs))
        if already_migrated:
            self._logger.info('Found %d run(s) already migrated, removing from failure log: %s', len(already_migrated), already_migrated[:10] if len(already_migrated) > 10 else already_migrated)
        if not runs_to_retry:
            self._logger.info('All failed runs are already migrated. Nothing to retry.')
            state.write_failure_log(failure_log, [])
            return 0
        self._logger.info('Migration Stage: Attempting to recover %d failed runs.', len(runs_to_retry))
        (successful, failed) = self._process_batch(runs_to_retry)
        all_successful = sorted(list(set(successful) | set(already_migrated)))
        remaining = sorted(list(set(failed_runs) - set(all_successful)))
        state.write_failure_log(failure_log, remaining)
        attempted_runs = successful + failed
        self._logger.info('Updating state tracking after recovery: %d newly migrated, %d total attempted in recovery', len(successful), len(attempted_runs))
        self._logger.debug('Querying all migrated runs for state update...')
        all_migrated = self._ucon.get_existing_runs()
        state.update_contiguous_run_state(self._config.app.migrate_state_file, sorted(list(all_migrated)))
        state.update_attempted_run_state(self._config.app.migrate_state_file, attempted_runs)
        if self._shutdown_check():
            self._logger.info('Migration Recovery: Shutdown requested - state saved, exiting gracefully')
            return 1
        self._logger.info('Migration Stage: Recovery complete. %d successful (%d already migrated, %d newly migrated), %d remaining.', len(all_successful), len(already_migrated), len(successful), len(remaining))
        return 1 if remaining else 0