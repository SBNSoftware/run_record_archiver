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
from .exceptions import ArchiverError, VerificationError
from .persistence import state
from .services.blob_creator import BlobCreator
from .services.reporting import send_failure_report


class Migrator:
    def __init__(
        self,
        config: Config,
        artdaq_client: ArtdaqDBClient,
        ucon_client: UconDBClient,
        blob_creator: BlobCreator,
        carbon_client: Optional[CarbonClient] = None,
    ):
        self._config = config
        self._artdaq = artdaq_client
        self._ucon = ucon_client
        self._blob_creator = blob_creator
        self._carbon_client = carbon_client
        self._logger = logging.getLogger(__name__)
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _get_runs_to_migrate(self, incremental: bool) -> List[int]:
        self._logger.info(
            "Migration Stage: Fetching runs (mode: %s).",
            "incremental" if incremental else "full",
        )
        artdaq_runs = self._artdaq.get_archived_runs()
        ucon_runs = self._ucon.get_existing_runs()
        runs_to_migrate = sorted(list(artdaq_runs - ucon_runs))

        if incremental:
            last_success = state.read_state(self._config.app.migrate_state_file).get(
                "last_contiguous_run", 0
            )
            runs_to_migrate = [run for run in runs_to_migrate if run > last_success]

        self._logger.info(
            "Migration Stage: Found %d runs to migrate.", len(runs_to_migrate)
        )
        return runs_to_migrate

    def _get_ucondb_data_url(self, run_number: int) -> str:
        base_url = self._config.ucon_db.server_url
        folder = self._config.ucon_db.folder_name
        obj = self._config.ucon_db.object_name
        return f"{base_url}/app/data/{folder}/{obj}/key={run_number}"

    def _process_run(self, run_number: int) -> bool:
        retries = self._config.app.run_process_retries
        for attempt in range(retries + 1):
            try:
                self._logger.info(
                    "Migration Stage: Processing run %d (attempt %d)",
                    run_number,
                    attempt + 1,
                )
                with tempfile.TemporaryDirectory(
                    prefix=f"migrator_{run_number}_"
                ) as tmpdir:
                    tmpdir_path = Path(tmpdir)

                    self._artdaq.export_run_configuration(run_number, tmpdir_path)
                    generated_blob = self._blob_creator.create_blob_from_directory(
                        run_number, tmpdir_path
                    )

                    self._ucon.upload_blob(run_number, generated_blob)
                    self._logger.info(
                        "Run %d: Successfully uploaded blob to UconDB.", run_number
                    )

                    data_url = self._get_ucondb_data_url(run_number)
                    self._logger.debug(
                        "Run %d: Verifying from URL: %s", run_number, data_url
                    )
                    response = requests.get(data_url, verify=False, timeout=30)
                    response.raise_for_status()
                    downloaded_blob = response.text

                    h1 = hashlib.md5(generated_blob.encode("utf-8")).hexdigest()
                    h2 = hashlib.md5(downloaded_blob.encode("utf-8")).hexdigest()
                    if h1 != h2:
                        raise VerificationError(
                            f"Run {run_number}: MD5 mismatch between generated ({h1}) "
                            f"and downloaded ({h2}) blobs."
                        )
                    self._logger.info(
                        "Run %d: Data verification successful.", run_number
                    )

                self._logger.info(
                    "Migration Stage: Successfully migrated and verified run %d",
                    run_number,
                )
                return True
            except (ArchiverError, requests.RequestException) as e:
                self._logger.error(
                    "Migration Stage: Failed run %d on attempt %d: %s",
                    run_number,
                    attempt + 1,
                    e,
                )
                if attempt < retries:
                    time.sleep(self._config.app.retry_delay_seconds)
        return False

    def _process_batch(self, runs: List[int]) -> List[int]:
        successful, failed = [], []
        with ThreadPoolExecutor(
            max_workers=self._config.app.parallel_workers
        ) as executor:
            future_to_run = {
                executor.submit(self._process_run, run): run for run in runs
            }
            for future in as_completed(future_to_run):
                run = future_to_run[future]
                try:
                    if future.result():
                        successful.append(run)
                    else:
                        failed.append(run)
                except Exception:
                    self._logger.exception(
                        "Migration Stage: Run %d failed with unhandled exception:", run
                    )
                    failed.append(run)

        if failed:
            state.append_to_failure_log(self._config.app.migrate_failure_log, failed)
            send_failure_report(failed, self._config.reporting, "migration")
        return successful

    def _update_metrics(
        self, processed: int, successful: int, max_run: Optional[int]
    ) -> None:
        if self._carbon_client and self._carbon_client.enabled:
            self._carbon_client.post_metric("migrate.runs_processed", processed)
            self._carbon_client.post_metric("migrate.runs_successful", successful)
            self._carbon_client.post_metric(
                "migrate.runs_failed", processed - successful
            )
            if max_run is not None:
                self._carbon_client.post_metric("migrate.last_successful_run", max_run)

    def run(self, incremental: bool) -> int:
        try:
            runs = self._get_runs_to_migrate(incremental)
        except ArchiverError as e:
            self._logger.critical(
                "Migration Stage: Failed to determine runs to migrate: %s", e
            )
            return 1
        if not runs:
            self._logger.info("Migration Stage: No new runs to migrate.")
            self._update_metrics(0, 0, None)
            return 0

        batch = runs[: self._config.app.batch_size]
        self._logger.info("Migration Stage: Processing batch of %d runs.", len(batch))
        successful = self._process_batch(batch)
        max_success = max(successful) if successful else None
        self._update_metrics(len(batch), len(successful), max_success)

        if incremental:
            state.update_contiguous_run_state(
                self._config.app.migrate_state_file, successful
            )
        return 1 if len(successful) < len(batch) else 0

    def run_failure_recovery(self) -> int:
        failure_log = self._config.app.migrate_failure_log
        if not failure_log.exists():
            self._logger.info("Migration Stage: No failure log, nothing to recover.")
            return 0
        failed_runs = state.parse_run_records_from_file(failure_log)
        if not failed_runs:
            self._logger.info("Migration Stage: No failed runs in log to recover.")
            return 0

        self._logger.info(
            "Migration Stage: Attempting to recover %d failed runs.", len(failed_runs)
        )
        successful = self._process_batch(failed_runs)
        remaining = sorted(list(set(failed_runs) - set(successful)))
        state.write_failure_log(failure_log, remaining)

        self._logger.info(
            "Migration Stage: Recovery complete (%d recovered, %d still failing).",
            len(successful),
            len(remaining),
        )
        return 1 if remaining else 0
