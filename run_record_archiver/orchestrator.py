import logging
import threading
import time
from typing import Optional
from .clients.artdaq import ArtdaqDBClient
from .clients.carbon import CarbonClient
from .clients.ucondb import UconDBClient
from .config import Config
from .exceptions import ArchiverError
from .importer import Importer
from .migrator import Migrator
from .persistence.lock import FileLock
from .reporter import Reporter
from .services.blob_creator import BlobCreator

class Orchestrator:

    def __init__(self, config: Config):
        self._config = config
        self._logger = logging.getLogger(__name__)
        self._current_stage: Optional[str] = None
        self._last_error: Optional[Exception] = None
        self._shutdown_requested = False
        self._shutdown_reason: Optional[str] = None
        self._lock_monitor_thread: Optional[threading.Thread] = None
        self._lock_monitor_stop_event = threading.Event()
        self._file_lock: Optional[FileLock] = None
        self._logger.info('Initializing Run Record Archiver components...')
        self._logger.debug('Configuration: work_dir=%s, batch_size=%d, workers=%d', config.app.work_dir, config.app.batch_size, config.app.parallel_workers)
        self.carbon_client = CarbonClient(host=config.carbon.host, port=config.carbon.port, metric_prefix=config.carbon.metric_prefix, enabled=config.carbon.enabled)
        self.artdaq_client = ArtdaqDBClient(database_uri=config.artdaq_db.database_uri, use_tools=config.artdaq_db.use_tools, remote_host=config.artdaq_db.remote_host, carbon_client=self.carbon_client, random_skip_percent=config.app_fuzz.random_skip_percent, random_error_percent=config.app_fuzz.random_error_percent, random_skip_retry=config.app_fuzz.random_skip_retry, random_error_retry=config.app_fuzz.random_error_retry)
        self.ucon_client = UconDBClient(config.ucon_db, self.carbon_client, random_skip_percent=config.app_fuzz.random_skip_percent, random_error_percent=config.app_fuzz.random_error_percent, random_skip_retry=config.app_fuzz.random_skip_retry, random_error_retry=config.app_fuzz.random_error_retry)
        self.blob_creator = BlobCreator()
        self.importer = Importer(config, self.artdaq_client)
        self.migrator = Migrator(config, self.artdaq_client, self.ucon_client, self.blob_creator, self.carbon_client)
        self.reporter = Reporter(config, self.artdaq_client, self.ucon_client)
        self.importer.set_shutdown_check(self.is_shutdown_requested)
        self.migrator.set_shutdown_check(self.is_shutdown_requested)
        self._logger.info('All components initialized successfully.')

    def run(self, incremental: bool, import_only: bool, migrate_only: bool, retry_failed_import: bool, retry_failed_migrate: bool, report_status: bool=False, compare_state: bool=False, validate: bool=False) -> int:
        import_rc = 0
        migrate_rc = 0
        if report_status:
            self._current_stage = 'Status Report'
            try:
                self.reporter.generate_report(compare_state=compare_state)
                return 0
            except ArchiverError as e:
                self._last_error = e
                self._logger.error('Status report failed: %s', str(e))
                raise
            except Exception as e:
                self._last_error = e
                self._logger.error('Status report failed with unexpected error: %s', str(e), exc_info=True)
                raise
            finally:
                self._current_stage = None
        mode_desc = self._get_execution_mode_description(incremental, import_only, migrate_only, retry_failed_import, retry_failed_migrate)
        self._logger.info('=== Execution Mode: %s ===', mode_desc)
        self.artdaq_client.set_incremental_mode(incremental)
        self.ucon_client.set_incremental_mode(incremental)
        try:
            if retry_failed_import:
                self._current_stage = 'Import Recovery'
                self._logger.info('=' * 60)
                self._logger.info('STAGE: Import Recovery - Retrying failed imports')
                self._logger.info('=' * 60)
                import_rc = self.importer.run_failure_recovery()
                self._log_stage_completion('Import Recovery', import_rc)
            elif not migrate_only and (not retry_failed_migrate):
                self._current_stage = 'Import'
                self._logger.info('=' * 60)
                self._logger.info('STAGE: Import - Importing runs from filesystem to ArtdaqDB')
                self._logger.info('Mode: %s', 'Incremental' if incremental else 'Full')
                self._logger.info('=' * 60)
                import_rc = self.importer.run(incremental=incremental, import_only=import_only)
                self._log_stage_completion('Import', import_rc)
            if retry_failed_migrate:
                self._current_stage = 'Migration Recovery'
                self._logger.info('=' * 60)
                self._logger.info('STAGE: Migration Recovery - Retrying failed migrations')
                self._logger.info('=' * 60)
                migrate_rc = self.migrator.run_failure_recovery()
                self._log_stage_completion('Migration Recovery', migrate_rc)
            elif not import_only and (not retry_failed_import):
                self._current_stage = 'Migration'
                self._logger.info('=' * 60)
                self._logger.info('STAGE: Migration - Migrating runs from ArtdaqDB to UconDB')
                self._logger.info('Mode: %s', 'Incremental' if incremental else 'Full')
                self._logger.info('=' * 60)
                migrate_rc = self.migrator.run(incremental=incremental, migrate_only=migrate_only, validate=validate)
                self._log_stage_completion('Migration', migrate_rc)
        except ArchiverError as e:
            self._last_error = e
            self._logger.error("Stage '%s' failed with error: %s", self._current_stage or 'Unknown', str(e))
            raise
        except Exception as e:
            self._last_error = e
            self._logger.error("Stage '%s' failed with unexpected error: %s", self._current_stage or 'Unknown', str(e), exc_info=True)
            raise
        finally:
            self._current_stage = None
            self._stop_lock_monitor()
        return import_rc or migrate_rc

    def _get_execution_mode_description(self, incremental: bool, import_only: bool, migrate_only: bool, retry_failed_import: bool, retry_failed_migrate: bool) -> str:
        if retry_failed_import:
            return 'Retry Failed Imports'
        if retry_failed_migrate:
            return 'Retry Failed Migrations'
        if import_only:
            return f"Import Only ({('Incremental' if incremental else 'Full')})"
        if migrate_only:
            return f"Migration Only ({('Incremental' if incremental else 'Full')})"
        return f"Full Pipeline ({('Incremental' if incremental else 'Full')})"

    def _log_stage_completion(self, stage_name: str, exit_code: int) -> None:
        if exit_code == 0:
            self._logger.info('✓ %s Stage completed successfully (exit code: %d)', stage_name, exit_code)
        else:
            self._logger.warning('✗ %s Stage completed with failures (exit code: %d)', stage_name, exit_code)

    def get_current_stage(self) -> Optional[str]:
        return self._current_stage

    def get_last_error(self) -> Optional[Exception]:
        return self._last_error

    def request_shutdown(self, reason: str='User request') -> None:
        if not self._shutdown_requested:
            self._shutdown_requested = True
            self._shutdown_reason = reason
            self._logger.info('Shutdown requested (%s) - will stop after current run completes', reason)

    def is_shutdown_requested(self) -> bool:
        return self._shutdown_requested

    def get_shutdown_reason(self) -> Optional[str]:
        return self._shutdown_reason

    def set_file_lock(self, file_lock: FileLock) -> None:
        self._file_lock = file_lock
        self._start_lock_monitor()

    def _start_lock_monitor(self) -> None:
        if self._file_lock is None:
            return
        self._lock_monitor_stop_event.clear()
        self._lock_monitor_thread = threading.Thread(target=self._lock_monitor_worker, name='LockMonitor', daemon=True)
        self._lock_monitor_thread.start()
        self._logger.debug('Lock monitor thread started (PID: %d)', self._file_lock.get_pid())

    def _lock_monitor_worker(self) -> None:
        poll_interval = 1.0
        while not self._lock_monitor_stop_event.is_set():
            if self._file_lock and (not self._file_lock.is_lock_file_valid()):
                self._logger.warning('=' * 70)
                self._logger.warning('LOCK FILE REMOVED - INITIATING GRACEFUL SHUTDOWN')
                self._logger.warning('Lock file: %s', self._file_lock.lock_file)
                self._logger.warning('Process will finish current run and then exit')
                self._logger.warning('=' * 70)
                self.request_shutdown(reason='Lock file removed')
                break
            for _ in range(int(poll_interval * 10)):
                if self._lock_monitor_stop_event.is_set():
                    break
                time.sleep(0.1)

    def recover_import_state(self) -> int:
        self._current_stage = 'Import State Recovery'
        self._logger.info('=' * 70)
        self._logger.info('IMPORT STATE RECOVERY')
        self._logger.info('=' * 70)
        try:
            self._logger.info('Querying filesystem for run records...')
            fs_runs = set()
            try:
                for p in self._config.source_files.run_records_dir.iterdir():
                    if p.is_dir() and p.name.isdigit():
                        fs_runs.add(int(p.name))
            except (IOError, PermissionError) as e:
                raise ArchiverError(f'Cannot read run records directory: {e}', stage='Import State Recovery', context={'directory': str(self._config.source_files.run_records_dir)}) from e
            self._logger.info('Found %d runs in filesystem', len(fs_runs))
            self._logger.info('Querying artdaqDB for archived runs...')
            artdaq_runs = self.artdaq_client.get_archived_runs()
            self._logger.info('Found %d runs in artdaqDB', len(artdaq_runs))
            if not artdaq_runs:
                self._logger.warning('No runs found in artdaqDB - setting state to 0')
                from .persistence import state
                state.write_state(self._config.app.import_state_file, {'last_contiguous_run': 0, 'last_attempted_run': 0})
                state.write_failure_log(self._config.app.import_failure_log, [])
                self._logger.info('✓ Import state recovered successfully')
                return 0
            last_attempted_run = max(artdaq_runs)
            self._logger.info('Last attempted run: %d', last_attempted_run)
            sorted_runs = sorted(artdaq_runs)
            if not sorted_runs:
                last_contiguous_run = 0
            else:
                last_contiguous_run = sorted_runs[0]
                for i in range(1, len(sorted_runs)):
                    if sorted_runs[i] == last_contiguous_run + 1:
                        last_contiguous_run = sorted_runs[i]
                    else:
                        break
            self._logger.info('Last contiguous run: %d', last_contiguous_run)
            missing_runs = []
            for run in sorted(fs_runs):
                if run > last_attempted_run:
                    break
                if run not in artdaq_runs:
                    missing_runs.append(run)
            self._logger.info('Found %d missing runs to add to failure log', len(missing_runs))
            from .persistence import state
            state.write_state(self._config.app.import_state_file, {'last_contiguous_run': last_contiguous_run, 'last_attempted_run': last_attempted_run})
            self._logger.info('✓ Written import_state.json')
            state.write_failure_log(self._config.app.import_failure_log, missing_runs)
            self._logger.info('✓ Written import_failure.log with %d runs', len(missing_runs))
            self._logger.info('=' * 70)
            self._logger.info('IMPORT STATE RECOVERY COMPLETE')
            self._logger.info('  Filesystem runs: %d', len(fs_runs))
            self._logger.info('  ArtdaqDB runs: %d', len(artdaq_runs))
            self._logger.info('  Last contiguous: %d', last_contiguous_run)
            self._logger.info('  Last attempted: %d', last_attempted_run)
            self._logger.info('  Missing runs: %d', len(missing_runs))
            if missing_runs:
                preview = missing_runs[:10] if len(missing_runs) > 10 else missing_runs
                self._logger.info('  Missing runs (preview): %s', preview)
            self._logger.info('=' * 70)
            return 0
        except ArchiverError:
            raise
        except Exception as e:
            self._logger.error('State recovery failed: %s', str(e), exc_info=True)
            raise ArchiverError(f'Import state recovery failed: {e}', stage='Import State Recovery') from e

    def recover_migrate_state(self) -> int:
        self._current_stage = 'Migration State Recovery'
        self._logger.info('=' * 70)
        self._logger.info('MIGRATION STATE RECOVERY')
        self._logger.info('=' * 70)
        try:
            self._logger.info('Querying artdaqDB for available runs...')
            artdaq_runs = self.artdaq_client.get_archived_runs()
            self._logger.info('Found %d runs in artdaqDB', len(artdaq_runs))
            self._logger.info('Querying UconDB for migrated runs...')
            ucon_runs = self.ucon_client.get_existing_runs()
            self._logger.info('Found %d runs in UconDB', len(ucon_runs))
            if not ucon_runs:
                self._logger.warning('No runs found in UconDB - setting state to 0')
                from .persistence import state
                state.write_state(self._config.app.migrate_state_file, {'last_contiguous_run': 0, 'last_attempted_run': 0})
                state.write_failure_log(self._config.app.migrate_failure_log, [])
                self._logger.info('✓ Migration state recovered successfully')
                return 0
            last_attempted_run = max(ucon_runs)
            self._logger.info('Last attempted run: %d', last_attempted_run)
            sorted_runs = sorted(ucon_runs)
            if not sorted_runs:
                last_contiguous_run = 0
            else:
                last_contiguous_run = sorted_runs[0]
                for i in range(1, len(sorted_runs)):
                    if sorted_runs[i] == last_contiguous_run + 1:
                        last_contiguous_run = sorted_runs[i]
                    else:
                        break
            self._logger.info('Last contiguous run: %d', last_contiguous_run)
            missing_runs = []
            for run in sorted(artdaq_runs):
                if run > last_attempted_run:
                    break
                if run not in ucon_runs:
                    missing_runs.append(run)
            self._logger.info('Found %d missing runs to add to failure log', len(missing_runs))
            from .persistence import state
            state.write_state(self._config.app.migrate_state_file, {'last_contiguous_run': last_contiguous_run, 'last_attempted_run': last_attempted_run})
            self._logger.info('✓ Written migrate_state.json')
            state.write_failure_log(self._config.app.migrate_failure_log, missing_runs)
            self._logger.info('✓ Written migrate_failure.log with %d runs', len(missing_runs))
            self._logger.info('=' * 70)
            self._logger.info('MIGRATION STATE RECOVERY COMPLETE')
            self._logger.info('  ArtdaqDB runs: %d', len(artdaq_runs))
            self._logger.info('  UconDB runs: %d', len(ucon_runs))
            self._logger.info('  Last contiguous: %d', last_contiguous_run)
            self._logger.info('  Last attempted: %d', last_attempted_run)
            self._logger.info('  Missing runs: %d', len(missing_runs))
            if missing_runs:
                preview = missing_runs[:10] if len(missing_runs) > 10 else missing_runs
                self._logger.info('  Missing runs (preview): %s', preview)
            self._logger.info('=' * 70)
            return 0
        except ArchiverError:
            raise
        except Exception as e:
            self._logger.error('State recovery failed: %s', str(e), exc_info=True)
            raise ArchiverError(f'Migration state recovery failed: {e}', stage='Migration State Recovery') from e

    def _stop_lock_monitor(self) -> None:
        if self._lock_monitor_thread and self._lock_monitor_thread.is_alive():
            self._lock_monitor_stop_event.set()
            self._lock_monitor_thread.join(timeout=2.0)
            self._logger.debug('Lock monitor thread stopped')