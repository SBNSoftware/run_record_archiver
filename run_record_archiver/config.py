from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .exceptions import ConfigurationError


class AppConfig:
    def __init__(self, data: Dict[str, Any]):
        self.work_dir = Path(data.get("work_dir", "/tmp/run_record_archiver"))
        self.import_state_file = Path(
            data.get("import_state_file", self.work_dir / "importer_state.json")
        )
        self.import_failure_log = Path(
            data.get("import_failure_log", self.work_dir / "import_failures.log")
        )
        self.migrate_state_file = Path(
            data.get("migrate_state_file", self.work_dir / "migrator_state.json")
        )
        self.migrate_failure_log = Path(
            data.get("migrate_failure_log", self.work_dir / "migrate_failures.log")
        )
        self.lock_file = Path(data.get("lock_file", self.work_dir / ".archiver.lock"))
        self.batch_size = int(data.get("batch_size", 50))
        self.parallel_workers = int(data.get("parallel_workers", 4))
        self.run_process_retries = int(data.get("run_process_retries", 2))
        self.retry_delay_seconds = int(data.get("retry_delay_seconds", 5))
        self.log_level = str(data.get("log_level", "INFO")).upper()
        log_file_path = data.get("log_file")
        self.log_file: Optional[Path] = Path(log_file_path) if log_file_path else None


class SourceFilesConfig:
    def __init__(self, data: Dict[str, Any]):
        try:
            self.run_records_dir = Path(data["run_records_dir"])
        except KeyError as e:
            raise ConfigurationError(
                "Source files config missing required key: 'run_records_dir'"
            ) from e


class ArtdaqDBConfig:
    def __init__(self, data: Dict[str, Any]):
        self.products_dir: Optional[str] = data.get("products_dir")
        self.spack_dir: Optional[str] = data.get("spack_dir")
        self.use_bulkloader = bool(data.get("use_bulkloader", False))
        self.remote_host: Optional[str] = data.get("remote_host")
        try:
            self.setup_script = Path(data["setup_script"])
            self.database_uri = str(data["database_uri"])
            self.fcl_conf_dir = Path(data["fcl_conf_dir"])
        except KeyError as e:
            raise ConfigurationError(
                f"ArtdaqDB config missing required key: '{e.args[0]}'"
            ) from e

        if not any([self.products_dir, self.spack_dir]):
            raise ConfigurationError(
                "ArtdaqDB config: either 'products_dir' or 'spack_dir' must be provided."
            )


class UconDBConfig:
    def __init__(self, data: Dict[str, Any]):
        self.timeout_seconds = int(data.get("timeout_seconds", 10))
        try:
            self.server_url = str(data["server_url"])
            self.folder_name = str(data["folder_name"])
            self.object_name = str(data["object_name"])
            self.writer_user = str(data["writer_user"])
            self.writer_password = str(data["writer_password"])
        except KeyError as e:
            raise ConfigurationError(
                f"UconDB config missing required key: '{e.args[0]}'"
            ) from e


class ReportingConfig:
    def __init__(self, data: Dict[str, Any]):
        self.send_email_on_error = bool(data.get("send_email_on_error", False))
        self.recipient_email: Optional[str] = data.get("recipient_email")
        self.sender_email: Optional[str] = data.get("sender_email")
        self.smtp_host: Optional[str] = data.get("smtp_host")
        self.smtp_port = int(data.get("smtp_port", 587))
        self.smtp_use_tls = bool(data.get("smtp_use_tls", True))
        self.smtp_user: Optional[str] = data.get("smtp_user")
        self.smtp_password: Optional[str] = data.get("smtp_password")

        if self.send_email_on_error and not all(
            [self.recipient_email, self.sender_email, self.smtp_host]
        ):
            raise ConfigurationError(
                "Reporting config: 'recipient_email', 'sender_email', and 'smtp_host' "
                "are required when 'send_email_on_error' is true."
            )


class CarbonConfig:
    def __init__(self, data: Dict[str, Any]):
        self.enabled = bool(data.get("enabled", False))
        self.host: Optional[str] = data.get("host")
        self.port = int(data.get("port", 2003))
        self.metric_prefix: Optional[str] = data.get("metric_prefix")

        if self.enabled and not all([self.host, self.metric_prefix]):
            raise ConfigurationError(
                "Carbon config: 'host' and 'metric_prefix' are required when enabled."
            )


class Config:
    def __init__(self, data: Dict[str, Any]):
        try:
            self.app = AppConfig(data.get("app", {}))
            self.source_files = SourceFilesConfig(data["source_files"])
            self.artdaq_db = ArtdaqDBConfig(data["artdaq_db"])
            self.ucon_db = UconDBConfig(data["ucon_db"])
            self.reporting = ReportingConfig(data.get("reporting", {}))
            self.carbon = CarbonConfig(data.get("carbon", {}))
        except KeyError as e:
            raise ConfigurationError(
                f"Top-level configuration key missing: '{e.args[0]}'"
            ) from e

    @staticmethod
    def from_file(path: str) -> "Config":
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                raise ConfigurationError(
                    f"Configuration file '{path}' is invalid or empty."
                )
            return Config(data)
        except FileNotFoundError as e:
            raise ConfigurationError(
                f"Configuration file not found at '{path}'."
            ) from e
        except yaml.YAMLError as e:
            raise ConfigurationError(
                f"Error parsing configuration file '{path}': {e}"
            ) from e
