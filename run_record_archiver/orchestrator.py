import logging

from .clients.artdaq import ArtdaqDBClient
from .clients.carbon import CarbonClient
from .clients.ucondb import UconDBClient
from .config import Config
from .importer import Importer
from .migrator import Migrator
from .services.blob_creator import BlobCreator


class Orchestrator:
    def __init__(self, config: Config):
        self._config = config
        self._logger = logging.getLogger(__name__)

        self.carbon_client = CarbonClient(
            host=config.carbon.host,
            port=config.carbon.port,
            metric_prefix=config.carbon.metric_prefix,
            enabled=config.carbon.enabled,
        )
        self.artdaq_client = ArtdaqDBClient(
            database_uri=config.artdaq_db.database_uri,
            use_bulkloader=config.artdaq_db.use_bulkloader,
            remote_host=config.artdaq_db.remote_host,
            carbon_client=self.carbon_client,
        )
        self.ucon_client = UconDBClient(config.ucon_db, self.carbon_client)
        self.blob_creator = BlobCreator()

        self.importer = Importer(config, self.artdaq_client)
        self.migrator = Migrator(
            config,
            self.artdaq_client,
            self.ucon_client,
            self.blob_creator,
            self.carbon_client,
        )

    def run(
        self,
        incremental: bool,
        import_only: bool,
        migrate_only: bool,
        retry_failed_import: bool,
        retry_failed_migrate: bool,
    ) -> int:
        import_rc = 0
        migrate_rc = 0

        if retry_failed_import:
            import_rc = self.importer.run_failure_recovery()
        elif not migrate_only:
            self._logger.info("Starting Import Stage...")
            import_rc = self.importer.run(incremental=incremental)
            self._logger.info("Import Stage finished with exit code %d.", import_rc)

        if retry_failed_migrate:
            migrate_rc = self.migrator.run_failure_recovery()
        elif not import_only:
            self._logger.info("Starting Migration Stage...")
            migrate_rc = self.migrator.run(incremental=incremental)
            self._logger.info("Migration Stage finished with exit code %d.", migrate_rc)

        return import_rc or migrate_rc
