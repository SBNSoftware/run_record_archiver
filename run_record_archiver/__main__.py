import argparse
import locale
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional
from run_record_archiver.config import Config
from run_record_archiver.constants import EXIT_CODE_SUCCESS, EXIT_CODE_ERROR, EXIT_CODE_UNEXPECTED_ERROR, EXIT_CODE_INTERRUPTED, SIGINT_IMMEDIATE_SHUTDOWN_COUNT, SIGINT_TIME_WINDOW_SECONDS, LOG_FILE_MAX_BYTES, LOG_FILE_MAX_AGE_SECONDS, LOG_FILE_BACKUP_COUNT
from run_record_archiver.exceptions import ArchiverError, LockExistsError
from run_record_archiver.log_handler import SizeAndTimeRotatingFileHandler
from run_record_archiver.orchestrator import Orchestrator
from run_record_archiver.persistence.lock import FileLock
os.environ['LANG'] = 'en_US.UTF-8'
os.environ['LANGUAGE'] = 'en_US.UTF-8'
os.environ['LC_ALL'] = 'en_US.UTF-8'
try:
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'C.UTF-8')
    except locale.Error:
        pass

class SignalHandler:

    def __init__(self):
        self.orchestrator: Optional[Orchestrator] = None
        self.shutdown_requested: bool = False
        self.sigint_count: int = 0
        self.last_sigint_time: float = 0.0
        self._logger = logging.getLogger(__name__)

    def set_orchestrator(self, orchestrator: Orchestrator) -> None:
        self.orchestrator = orchestrator

    def handle_sigint(self, signum: int, frame) -> None:
        current_time = time.time()
        if current_time - self.last_sigint_time > SIGINT_TIME_WINDOW_SECONDS:
            self.sigint_count = 0
        self.sigint_count += 1
        self.last_sigint_time = current_time
        if self.sigint_count >= SIGINT_IMMEDIATE_SHUTDOWN_COUNT:
            self._logger.warning('=' * 70)
            self._logger.warning('IMMEDIATE SHUTDOWN REQUESTED (3x Ctrl-C)')
            self._logger.warning('=' * 70)
            logging.shutdown()
            os._exit(EXIT_CODE_INTERRUPTED)
        elif self.sigint_count == 1:
            self._logger.warning('=' * 70)
            self._logger.warning('GRACEFUL SHUTDOWN REQUESTED (Ctrl-C)')
            self._logger.warning('Current run will finish processing...')
            self._logger.warning('Press Ctrl-C two more times within %d seconds for immediate shutdown', SIGINT_TIME_WINDOW_SECONDS)
            self._logger.warning('=' * 70)
            self.shutdown_requested = True
            if self.orchestrator:
                self.orchestrator.request_shutdown()
        else:
            remaining = SIGINT_IMMEDIATE_SHUTDOWN_COUNT - self.sigint_count
            self._logger.warning('Ctrl-C pressed %d/%d times - press %d more for immediate shutdown', self.sigint_count, SIGINT_IMMEDIATE_SHUTDOWN_COUNT, remaining)

    def is_shutdown_requested(self) -> bool:
        return self.shutdown_requested

def setup_logging(level: str, log_file: Optional[Path], verbose: bool=False) -> None:
    log_level_str = 'DEBUG' if verbose else level
    try:
        log_level = getattr(logging, log_level_str.upper())
    except AttributeError:
        log_level = logging.INFO
        logging.basicConfig()
        logging.warning("Invalid log level '%s', defaulting to INFO.", log_level_str)
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)
    if log_file:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = SizeAndTimeRotatingFileHandler(filename=str(log_file), max_bytes=LOG_FILE_MAX_BYTES, max_age_seconds=LOG_FILE_MAX_AGE_SECONDS, backup_count=LOG_FILE_BACKUP_COUNT)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except (IOError, PermissionError) as e:
            root_logger.error("Failed to configure file logging at '%s': %s", log_file, e)

def main() -> None:
    help_flags = ['-h', '--help', '/?', '/h', '/help']
    if any((flag in sys.argv for flag in help_flags)):
        for (i, arg) in enumerate(sys.argv):
            if arg in ['/?', '/h', '/help']:
                sys.argv[i] = '--help'
    epilog_text = '\nDESCRIPTION:\n  The Run Record Archiver is a two-stage pipeline that archives artdaq run\n  record configurations from a source filesystem through an intermediate\n  artdaqDB database to a final UconDB server.\n\n  Stage 1 (Import):  Filesystem → artdaqDB (MongoDB or FilesystemDB)\n  Stage 2 (Migrate): artdaqDB → UconDB (via text blob upload)\n\nEXECUTION MODES (mutually exclusive):\n  [default]                Run full pipeline (import → migration)\n  --import-only            Run import stage only\n  --migrate-only           Run migration stage only\n  --retry-failed-import    Retry runs from import failure log\n  --retry-failed-migrate   Retry runs from migration failure log\n  --report-status          Generate status report (no processing)\n  --recover-import-state   Recover import state from filesystem/artdaqDB\n  --recover-migrate-state  Recover migration state from artdaqDB/UconDB\n\nADDITIONAL FLAGS:\n  --incremental          Process only runs newer than last successful\n  --compare-state        Generate status report and compare with saved state files\n                         (automatically enables --report-status)\n  --validate             Validate blob metadata after migration\n  -v, --verbose          Enable DEBUG logging\n\nEXAMPLES:\n  python -m run_record_archiver config.yaml\n\n  python -m run_record_archiver config.yaml --incremental\n\n  python -m run_record_archiver config.yaml --import-only\n\n  python -m run_record_archiver config.yaml --migrate-only --validate\n\n  python -m run_record_archiver config.yaml --retry-failed-import\n\n  python -m run_record_archiver config.yaml --report-status\n\n  python -m run_record_archiver config.yaml --report-status --compare-state\n  python -m run_record_archiver config.yaml --compare-state\n\n  python -m run_record_archiver config.yaml --recover-import-state\n\n  python -m run_record_archiver config.yaml --recover-migrate-state\n\n  python -m run_record_archiver config.yaml --incremental -v\n\nEXIT CODES:\n  0   Success\n  1   Known error (configuration, lock, archival failure)\n  2   Unexpected error (see logs for details)\n  130 Interrupted by user signal (Ctrl-C)\n\nSIGNAL HANDLING:\n  Ctrl-C (once)   Graceful shutdown after current run completes\n  Ctrl-C (3x)     Immediate shutdown (within 2 seconds)\n\nFor more information, see documentation in run_record_archiver/ directory.\n'
    parser = argparse.ArgumentParser(prog='run_record_archiver', description='Archive artdaq run records from filesystem to artdaqDB to UconDB.', epilog=epilog_text, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('config_file', type=str, nargs='?', default='config.yaml', help='Path to the YAML configuration file (default: config.yaml).')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable DEBUG level logging, overriding config.')
    parser.add_argument('--incremental', action='store_true', help='Run in incremental mode for both stages.')
    parser.add_argument('--compare-state', action='store_true', help='Generate status report and compare with saved state files (automatically enables --report-status).')
    parser.add_argument('--validate', action='store_true', help='Validate blob metadata after migration (recommended with --migrate-only).')
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--import-only', action='store_true', help='Run only the filesystem to artdaqDB import stage.')
    mode_group.add_argument('--migrate-only', action='store_true', help='Run only the artdaqDB to UconDB migration stage.')
    mode_group.add_argument('--retry-failed-import', action='store_true', help='Retry failed runs from the import failure log.')
    mode_group.add_argument('--retry-failed-migrate', action='store_true', help='Retry failed runs from the migration failure log.')
    mode_group.add_argument('--report-status', action='store_true', help='Generate status report showing run availability across all data sources.')
    mode_group.add_argument('--recover-import-state', action='store_true', help='Recover import state by querying filesystem and artdaqDB (rebuilds state files).')
    mode_group.add_argument('--recover-migrate-state', action='store_true', help='Recover migration state by querying artdaqDB and UconDB (rebuilds state files).')
    args = parser.parse_args()
    if args.compare_state and (not args.report_status):
        args.report_status = True
    exit_code = EXIT_CODE_SUCCESS
    config: Optional[Config] = None
    error_occurred = False
    error_stage = None
    sig_handler = SignalHandler()
    try:
        config = Config.from_file(args.config_file)
        config.app.work_dir.mkdir(parents=True, exist_ok=True)
        setup_logging(config.app.log_level, config.app.log_file, args.verbose)
        logger = logging.getLogger(__name__)
        logger.info('=' * 70)
        logger.info('Run Record Archiver Starting')
        logger.info('Config: %s', args.config_file)
        logger.info('=' * 70)
        signal.signal(signal.SIGINT, sig_handler.handle_sigint)
        logger.debug('Registered SIGINT handler for graceful shutdown')
        with FileLock(config.app.lock_file) as file_lock:
            orchestrator = Orchestrator(config)
            sig_handler.set_orchestrator(orchestrator)
            orchestrator.set_file_lock(file_lock)
            if args.recover_import_state:
                exit_code = orchestrator.recover_import_state()
            elif args.recover_migrate_state:
                exit_code = orchestrator.recover_migrate_state()
            else:
                exit_code = orchestrator.run(incremental=args.incremental, import_only=args.import_only, migrate_only=args.migrate_only, retry_failed_import=args.retry_failed_import, retry_failed_migrate=args.retry_failed_migrate, report_status=args.report_status, compare_state=args.compare_state, validate=args.validate)
            logger.info('=' * 70)
            if sig_handler.is_shutdown_requested() or orchestrator.is_shutdown_requested():
                shutdown_reason = orchestrator.get_shutdown_reason() or 'User interrupt'
                logger.warning('✓ GRACEFUL SHUTDOWN COMPLETED')
                logger.warning('Reason: %s', shutdown_reason)
                exit_code = EXIT_CODE_INTERRUPTED
            elif exit_code == EXIT_CODE_SUCCESS:
                logger.info('✓ EXECUTION COMPLETED SUCCESSFULLY')
            else:
                logger.warning('✗ EXECUTION COMPLETED WITH FAILURES (exit code: %d)', exit_code)
            logger.info('=' * 70)
    except (LockExistsError, ArchiverError) as e:
        error_occurred = True
        if sig_handler.orchestrator:
            error_stage = sig_handler.orchestrator.get_current_stage()
        log_level = logging.WARNING if isinstance(e, LockExistsError) else logging.CRITICAL
        if not config:
            logging.basicConfig(level=log_level)
        logger = logging.getLogger(__name__)
        logger.log(log_level, '=' * 70)
        logger.log(log_level, 'ERROR SUMMARY')
        logger.log(log_level, '=' * 70)
        if error_stage:
            logger.log(log_level, 'Failed Stage: %s', error_stage)
        logger.log(log_level, 'Error Type: %s', e.__class__.__name__)
        logger.log(log_level, 'Error Message: %s', str(e))
        if hasattr(e, 'get_summary'):
            logger.debug('Detailed Error: %s', e.get_summary())
        logger.log(log_level, '=' * 70)
        exit_code = EXIT_CODE_ERROR
    except Exception as e:
        error_occurred = True
        if sig_handler.orchestrator:
            error_stage = sig_handler.orchestrator.get_current_stage()
        if not config:
            logging.basicConfig(level=logging.CRITICAL)
        logger = logging.getLogger(__name__)
        logger.critical('=' * 70)
        logger.critical('UNEXPECTED ERROR SUMMARY')
        logger.critical('=' * 70)
        if error_stage:
            logger.critical('Failed Stage: %s', error_stage)
        logger.critical('Error Type: %s', e.__class__.__name__)
        logger.critical('Error Message: %s', str(e))
        logger.critical('=' * 70)
        logger.critical('Full traceback:', exc_info=True)
        exit_code = EXIT_CODE_UNEXPECTED_ERROR
    finally:
        if config:
            logger = logging.getLogger(__name__)
            if error_occurred:
                logger.info('Archiver terminated due to error.')
                if error_stage:
                    logger.info('Check logs for details about %s stage failure.', error_stage)
            else:
                logger.info('Archiver execution complete.')
        logging.shutdown()
        os._exit(exit_code)
if __name__ == '__main__':
    main()