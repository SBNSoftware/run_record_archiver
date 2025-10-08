import logging
import re
import shutil
from pathlib import Path
from typing import List

from ..exceptions import FclPreperationError


class FclPreparer:
    def __init__(self, fcl_conf_dir: Path):
        self._logger = logging.getLogger(__name__)
        self.fcl_conf_dir = fcl_conf_dir
        if not self.fcl_conf_dir.is_dir():
            raise FclPreperationError(
                f"FCL confdir '{self.fcl_conf_dir}' is not a directory."
            )

    def prepare_fcl_for_archive(self, run_dir: Path, tmpdir_path: Path) -> str:
        try:
            shutil.copytree(run_dir, tmpdir_path, dirs_exist_ok=True)
            for src_path in tmpdir_path.glob("*.txt"):
                if src_path.name == "metadata.txt":
                    dest_path = tmpdir_path / "metadata.fcl"
                    dest_path.write_text(self._fhiclize_document(src_path))
                src_path.unlink()

            schema_src = self.fcl_conf_dir / "schema.fcl"
            if not schema_src.is_file():
                raise FclPreperationError(f"Schema not found at {schema_src}")
            shutil.copy(schema_src, tmpdir_path)
            return self._resolve_config_name(run_dir)
        except (IOError, shutil.Error) as e:
            raise FclPreperationError(f"Error preparing FCL for archive: {e}") from e

    def prepare_fcl_for_update(self, run_dir: Path, tmpdir_path: Path) -> None:
        try:
            rh2_content = []
            if (metadata_path := run_dir / "metadata.txt").exists():
                for line in metadata_path.read_text().splitlines():
                    match = re.search(r"^DAQInterface stop time:\s+(.*)", line)
                    if match:
                        rh2_content.append(f'DAQInterface_stop_time: "{match.group(1)}"')
            (tmpdir_path / "RunHistory2.fcl").write_text("\n".join(rh2_content))
        except IOError as e:
            raise FclPreperationError(f"Error preparing FCL for update: {e}") from e

    def _fhiclize_document(self, filepath: Path) -> str:
        fhiclized_lines: List[str] = []
        try:
            for line in filepath.read_text().splitlines():
                if match := re.match(r"^\s*([^:]+?)\s*:\s*(.*)", line):
                    key, value = match.groups()
                    key = re.sub(r"[\s()/]", "_", key.strip())
                    value = value.strip().strip("'\"").replace('"', '\\"')
                    fhiclized_lines.append(f'{key}: "{value}"')
        except IOError as e:
            raise FclPreperationError(f"Could not FHiCLize {filepath}: {e}") from e
        return "\n".join(fhiclized_lines)

    def _resolve_config_name(self, run_dir: Path) -> str:
        metadata_file = run_dir / "metadata.txt"
        if metadata_file.exists():
            try:
                for line in metadata_file.read_text().splitlines():
                    if match := re.match(r"^Config name:\s+(.*)", line):
                        if name := match.group(1).strip():
                            return name.replace("/", "_")
            except IOError as e:
                self._logger.warning("Could not read metadata file %s: %s", run_dir, e)
        return "standard"
