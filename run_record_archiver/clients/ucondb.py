import logging
from typing import Optional, Set

import urllib3
from ucondb.webapi import UConDBClient as UConDBAPIClient

from ..config import UconDBConfig
from ..exceptions import UconDBError
from ..utils import performance_monitor
from .carbon import CarbonClient


class UconDBClient:
    def __init__(
        self, config: UconDBConfig, carbon_client: Optional[CarbonClient] = None
    ):
        self.carbon_client = carbon_client
        self._logger = logging.getLogger(__name__)
        self._config = config
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        try:
            self._logger.info(
                "Initializing UconDB client for server: %s", config.server_url
            )
            self.client = UConDBAPIClient(
                server_url=config.server_url,
                timeout=config.timeout_seconds,
                username=config.writer_user,
                password=config.writer_password,
            )
            self._logger.info(
                "Successfully connected to UconDB server, version: %s",
                self.client.version(),
            )
        except Exception as e:
            raise UconDBError(f"Failed to initialize UConDB client: {e}") from e

    @performance_monitor
    def get_existing_runs(self) -> Set[int]:
        try:
            results = self.client.lookup_versions(
                folder_name=self._config.folder_name,
                object_name=self._config.object_name,
            )
            return {int(r["key"]) for r in results if r.get("key", "").isdigit()}
        except Exception as e:
            raise UconDBError(f"Failed to look up versions in UconDB: {e}") from e

    @performance_monitor
    def upload_blob(self, run_number: int, blob_content: str) -> str:
        try:
            key = str(run_number)
            version = self.client.put(
                folder_name=self._config.folder_name,
                object_name=self._config.object_name,
                data=blob_content,
                key=key,
                tags=key,
            )
            if version is None:
                raise UconDBError(
                    "UConDBClient.put returned None, indicating an upload error."
                )
            return version
        except Exception as e:
            raise UconDBError(f"Failed to upload blob for run {run_number}: {e}") from e
