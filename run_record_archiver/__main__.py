import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from run_record_archiver.config import Config
from run_record_archiver.exceptions import ArchiverError, LockExistsError
from run_record_archiver.orchestrator import Orchestrator
from run_record_archiver.persistence.lock import FileLock


def setup_logging(
    level: str, log_file: Optional[Path], verbose: bool = False
) -> None:
    log_level_str = "DEBUG" if verbose else level
    try:
        log_level = getattr(logging, log_level_str.upper())
    except AttributeError:
        log_level = logging.INFO
        logging.basicConfig()
        logging.warning("Invalid log level '%s', defaulting to INFO.", log_level_str)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    if log_file:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_file, maxBytes=10 * 1024 * 1024, backupCount=5
            )
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except (IOError, PermissionError) as e:
            root_logger.error("Failed to configure file logging at '%s': %s", log_file, e)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Archive run records from filesystem to artdaqDB, then to UconDB."
    )
    parser.add_argument(
        "config_file", type=str, help="Path to the YAML configuration file."
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable DEBUG level logging, overriding config.",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Run in incremental mode for both stages.",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--import-only",
        action="store_true",
        help="Run only the filesystem to artdaqDB import stage.",
    )
    mode_group.add_argument(
        "--migrate-only",
        action="store_true",
        help="Run only the artdaqDB to UconDB migration stage.",
    )
    mode_group.add_argument(
        "--retry-failed-import",
        action="store_true",
        help="Retry failed runs from the import failure log.",
    )
    mode_group.add_argument(
        "--retry-failed-migrate",
        action="store_true",
        help="Retry failed runs from the migration failure log.",
    )

    args = parser.parse_args()
    exit_code = 0
    config: Optional[Config] = None

    try:
        config = Config.from_file(args.config_file)
        config.app.work_dir.mkdir(parents=True, exist_ok=True)
        setup_logging(config.app.log_level, config.app.log_file, args.verbose)
        logger = logging.getLogger(__name__)

        with FileLock(config.app.lock_file):
            logger.info("Run Record Archiver starting.")
            orchestrator = Orchestrator(config)
            exit_code = orchestrator.run(
                incremental=args.incremental,
                import_only=args.import_only,
                migrate_only=args.migrate_only,
                retry_failed_import=args.retry_failed_import,
                retry_failed_migrate=args.retry_failed_migrate,
            )
            logger.info(
                "Run Record Archiver finished with final exit code %d.", exit_code
            )

    except (LockExistsError, ArchiverError) as e:
        log_level = logging.WARNING if isinstance(e, LockExistsError) else logging.CRITICAL
        if not config:
            logging.basicConfig(level=log_level)
        logging.log(log_level, "An application error occurred: %s", e)
        exit_code = 1
    except Exception as e:
        if not config:
            logging.basicConfig(level=logging.CRITICAL)
        logging.critical("An unexpected error terminated: %s", e, exc_info=True)
        exit_code = 2
    finally:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
