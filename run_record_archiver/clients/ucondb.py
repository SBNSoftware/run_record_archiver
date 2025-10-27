import logging
import random
from typing import Optional, Set
import urllib3
from ucondb.webapi import UConDBClient as UConDBAPIClient
from ..config import UconDBConfig
from ..exceptions import UconDBError, FuzzSkipError
from ..utils import performance_monitor
from .carbon import CarbonClient

class UconDBClient:

    def __init__(self, config: UconDBConfig, carbon_client: Optional[CarbonClient]=None, random_skip_percent: int=0, random_error_percent: int=0, random_skip_retry: bool=False, random_error_retry: bool=False):
        self.carbon_client = carbon_client
        self._logger = logging.getLogger(__name__)
        self._config = config
        self.random_skip_percent = random_skip_percent
        self.random_error_percent = random_error_percent
        self.random_skip_retry = random_skip_retry
        self.random_error_retry = random_error_retry
        self._incremental_mode = False
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        try:
            self._logger.info('Initializing UconDB client for server: %s', config.server_url)
            self.client = UConDBAPIClient(server_url=config.server_url, timeout=config.timeout_seconds, username=config.writer_user, password=config.writer_password)
            self._logger.info('Successfully connected to UconDB server, version: %s', self.client.version())
        except Exception as e:
            raise UconDBError(f'Failed to initialize UConDB client: {e}') from e

    def set_incremental_mode(self, incremental: bool) -> None:
        self._incremental_mode = incremental

    @performance_monitor
    def get_existing_runs(self) -> Set[int]:
        try:
            results = self.client.lookup_versions(folder_name=self._config.folder_name, object_name=self._config.object_name)
            return {int(r['key']) for r in results if r.get('key', '').isdigit()}
        except Exception as e:
            raise UconDBError(f'Failed to look up versions in UconDB: {e}') from e

    @performance_monitor
    def upload_blob(self, run_number: int, blob_content: str) -> str:
        if not self._incremental_mode:
            if self.random_skip_percent > 0:
                if random.randint(1, 100) <= self.random_skip_percent:
                    if self.random_skip_retry:
                        self._logger.warning('[FUZZ] Permanently skipping run %d - will NOT retry (random_skip_retry=true)', run_number)
                        raise FuzzSkipError(f'[FUZZ] Permanent skip for run {run_number} (random_skip_retry=true)', run_number=run_number)
                    else:
                        self._logger.warning('[FUZZ] Randomly skipping run %d - will retry later (random_skip_percent=%d%%)', run_number, self.random_skip_percent)
                        return f'fuzz_skip_{run_number}'
            if self.random_error_percent > 0:
                if random.randint(1, 100) <= self.random_error_percent:
                    if random.choice([True, False]):
                        if self.random_error_retry:
                            self._logger.warning('[FUZZ] Permanently failing run %d - will NOT retry (random_error_retry=true)', run_number)
                            raise FuzzSkipError(f'[FUZZ] Permanent error for run {run_number} (random_error_retry=true)', run_number=run_number)
                        else:
                            self._logger.warning('[FUZZ] Randomly failing run %d - will retry later (random_error_percent=%d%%)', run_number, self.random_error_percent)
                            raise UconDBError(f'[FUZZ] Random test failure for run {run_number}', run_number=run_number)
        try:
            key = str(run_number)
            version = self.client.put(folder_name=self._config.folder_name, object_name=self._config.object_name, data=blob_content, key=key, tags=key)
            if version is None:
                raise UconDBError('UConDBClient.put returned None, indicating an upload error.')
            return version
        except Exception as e:
            error_str = str(e)
            if 'already exists' in error_str.lower() and str(run_number) in error_str:
                self._logger.warning('Run %d already exists in UconDB, treating as success', run_number)
                return f'existing_{run_number}'
            raise UconDBError(f'Failed to upload blob for run {run_number}: {e}') from e

    @performance_monitor
    def get_data(self, run_number: int) -> str:
        try:
            key = str(run_number)
            blob_bytes = self.client.get_data(folder_name=self._config.folder_name, data_key=key)
            if isinstance(blob_bytes, bytes):
                return blob_bytes.decode('utf-8')
            return blob_bytes
        except Exception as e:
            raise UconDBError(f'Failed to download blob for run {run_number}: {e}') from e