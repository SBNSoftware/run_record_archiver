import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set

from ..exceptions import ArtdaqDBError
from ..services.process_runner import run_bulkloader
from ..utils import performance_monitor
from .carbon import CarbonClient

try:
    import conftoolp
except ImportError as e:
    raise ImportError(
        "Failed to import 'conftoolp'. Ensure artdaq_database env is set up."
    ) from e


class ArtdaqDBClient:
    def __init__(
        self,
        database_uri: str,
        use_bulkloader: bool,
        remote_host: Optional[str],
        carbon_client: Optional[CarbonClient] = None,
    ):
        self.carbon_client = carbon_client
        self._logger = logging.getLogger(__name__)
        self.database_uri = database_uri
        self.use_bulkloader = use_bulkloader
        self.remote_host = remote_host or os.environ.get("ARTDAQ_DATABASE_REMOTEHOST")
        conftoolp.set_default_locale()
        conftoolp.enable_trace()

    @staticmethod
    def _get_archive_uri(uri: str) -> str:
        match = re.match(r".*://.*?/(.*?(?=(?:\?)|$))", uri)
        if not match or not match.group(1):
            raise ArtdaqDBError(f"Invalid database URI format: {uri}")
        return uri.replace(match.group(1), match.group(1) + "_archive")

    def _list_versions(self, collection_name: str) -> List[str]:
        query = {
            "operation": "findversions",
            "dataformat": "csv",
            "collection": collection_name,
            "filter": {"entities.name": "*"},
        }
        success, result_csv = conftoolp.find_versions(json.dumps(query))
        if not success:
            raise ArtdaqDBError(
                f"Failed to list versions for {collection_name}: {result_csv}"
            )
        return result_csv.split(",") if result_csv else []

    @staticmethod
    def _composition_reader(
        subsets: List[str], layout: Dict[str, Any], files: List[Path]
    ) -> Generator[tuple[str, str, str], None, None]:
        for file_path in files:
            for subset in subsets:
                if subset not in layout:
                    continue
                for rule in layout[subset]:
                    if match := re.match(rule["pattern"], str(file_path)):
                        entity_name = match.group(2)
                        if "entity" in rule:
                            try:
                                entity_name = eval(rule["entity"], {"match": match})
                            except Exception as e:
                                raise ArtdaqDBError(
                                    f"Failed to eval entity rule '{rule['entity']}': {e}"
                                ) from e
                        yield (rule["collection"], entity_name, str(file_path))

    @staticmethod
    def _hash_configuration(entity_userdata_map: Dict[str, str]) -> None:
        if not entity_userdata_map:
            return
        hashes = [
            f"{entity}:{hashlib.md5(content.encode('utf-8')).hexdigest()}"
            for entity, content in sorted(entity_userdata_map.items())
            if entity != "schema"
        ]
        config_hash = hashlib.md5(",".join(hashes).encode("utf-8")).hexdigest()
        hashes.append(f"configuration:{config_hash}")
        entity_userdata_map["hashes"] = "\n".join(hashes)

    @performance_monitor
    def get_archived_runs(self) -> Set[int]:
        original_uri = os.environ.get("ARTDAQ_DATABASE_URI", self.database_uri)
        archive_uri = self._get_archive_uri(original_uri)
        try:
            os.environ["ARTDAQ_DATABASE_URI"] = archive_uri
            query = {
                "operation": "findconfigs",
                "dataformat": "gui",
                "filter": {"configurations.name": "*"},
            }
            success, result_json = conftoolp.find_configurations(json.dumps(query))
            if not success:
                raise ArtdaqDBError(f"Failed to get configurations: {result_json}")

            configs = json.loads(result_json)["search"]
            return {
                int(match.group(1))
                for config in configs
                if (match := re.match(r"^\s*(\d+)/", config.get("name", "")))
            }
        except (json.JSONDecodeError, KeyError) as e:
            raise ArtdaqDBError(f"Failed to parse configurations list: {e}") from e
        finally:
            os.environ["ARTDAQ_DATABASE_URI"] = original_uri

    @performance_monitor
    def archive_run(
        self, run_number: int, config_name: str, prepared_fcl_dir: Path, update: bool
    ) -> None:
        if self.use_bulkloader:
            self._archive_with_bulkloader(
                config_name, run_number, prepared_fcl_dir, update
            )
        else:
            self._archive_with_conftoolp(
                config_name, run_number, prepared_fcl_dir, update
            )

    def _archive_with_bulkloader(
        self, config_name: str, run_number: int, tmpdir_path: Path, update: bool
    ) -> None:
        original_uri = os.environ.get("ARTDAQ_DATABASE_URI", self.database_uri)
        archive_uri = self._get_archive_uri(original_uri)
        try:
            os.environ["ARTDAQ_DATABASE_URI"] = archive_uri
            found_versions = self._list_versions("SystemLayout")
        finally:
            os.environ["ARTDAQ_DATABASE_URI"] = original_uri

        full_config_name = f"{run_number}/{config_name}"
        is_present = any(v.startswith(full_config_name) for v in found_versions)

        if is_present and not update:
            raise ArtdaqDBError(f"Configuration {full_config_name} is already archived.")
        if not is_present and update:
            raise ArtdaqDBError(
                f"Configuration {full_config_name} not found for update."
            )
        run_bulkloader(
            run_number, config_name, tmpdir_path, archive_uri, self.remote_host
        )

    def _archive_with_conftoolp(
        self, config_name: str, run_number: int, tmpdir_path: Path, update: bool
    ) -> None:
        original_uri = os.environ.get("ARTDAQ_DATABASE_URI", self.database_uri)
        archive_uri = self._get_archive_uri(original_uri)
        try:
            os.environ["ARTDAQ_DATABASE_URI"] = archive_uri
            schema_path = tmpdir_path / "schema.fcl"
            if not schema_path.is_file():
                raise ArtdaqDBError(f"Schema file not found: {schema_path}")
            schema = json.loads(
                conftoolp.fhicl_to_json(schema_path.read_text(), str(schema_path))[1]
            )["document"]["data"]["main"]
            composition = list(
                self._composition_reader(
                    ["run_history", "system_layout"],
                    schema,
                    list(tmpdir_path.rglob("*.fcl")),
                )
            )
            entity_userdata_map = {
                entity: Path(path).read_text() for _, entity, path in composition
            }
            if not update:
                self._hash_configuration(entity_userdata_map)

            full_config_name = f"{run_number}/{config_name}"
            version = full_config_name
            found_versions = self._list_versions("SystemLayout")
            is_present = any(v.startswith(full_config_name) for v in found_versions)

            if is_present:
                if not update:
                    raise ArtdaqDBError(
                        f"Configuration {full_config_name} is already archived."
                    )
                run_versions = [v for v in found_versions if v.startswith(full_config_name)]
                latest_v_num = max(
                    (
                        int(m.group(1))
                        for v in run_versions
                        if (
                            m := re.match(
                                rf"^{re.escape(full_config_name)}v(\d+)$", v
                            )
                        )
                    ),
                    default=0,
                )
                version = f"{full_config_name}v{latest_v_num + 1}"
            elif update:
                raise ArtdaqDBError(
                    f"Configuration {full_config_name} not found for update."
                )

            self._logger.info("Storing config %s version %s", full_config_name, version)
            composition_map = {entity: coll for coll, entity, _ in composition}
            for entity, content in entity_userdata_map.items():
                collection = (
                    composition_map.get(entity, "RunHistory")
                    if entity != "schema"
                    else "SystemLayout"
                )
                query = {
                    "operation": "store",
                    "dataformat": "fhicl",
                    "collection": collection,
                    "filter": {
                        "configurations.name": full_config_name,
                        "version": version,
                        "entities.name": entity,
                        "runs.name": str(run_number),
                    },
                }
                success, result_msg = conftoolp.write_document(
                    json.dumps(query), content
                )
                if not success:
                    raise ArtdaqDBError(
                        f"Failed to write doc for entity {entity}: {result_msg}"
                    )
        finally:
            os.environ["ARTDAQ_DATABASE_URI"] = original_uri

    @performance_monitor
    def export_run_configuration(self, run_number: int, destination_dir: Path) -> None:
        original_uri = os.environ.get("ARTDAQ_DATABASE_URI", self.database_uri)
        archive_uri = self._get_archive_uri(original_uri)
        try:
            os.environ["ARTDAQ_DATABASE_URI"] = archive_uri
            config_name = f"{run_number}/*"
            composition_query = {
                "operation": "buildfilter",
                "dataformat": "gui",
                "filter": {"configurations.name": config_name},
            }
            success, result_json = conftoolp.configuration_composition(
                json.dumps(composition_query)
            )
            if not success:
                raise ArtdaqDBError(
                    f"Failed to get composition for run {run_number}: {result_json}"
                )

            composition = json.loads(result_json)
            for item in composition.get("search", []):
                doc_query = item.get("query")
                if not doc_query:
                    continue
                doc_query["dataformat"] = "origin"
                success, content = conftoolp.read_document(json.dumps(doc_query))
                if not success:
                    raise ArtdaqDBError(
                        f"Failed to read doc with query '{doc_query}': {content}"
                    )

                entity_name = doc_query.get("filter", {}).get("entities.name")
                if entity_name:
                    (destination_dir / f"{entity_name}.fcl").write_text(content)

        except (ArtdaqDBError, IOError, json.JSONDecodeError) as e:
            raise ArtdaqDBError(
                f"Failed to export configuration for run {run_number}: {e}"
            ) from e
        finally:
            os.environ["ARTDAQ_DATABASE_URI"] = original_uri
