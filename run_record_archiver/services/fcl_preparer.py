import logging
import re
import shutil
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set
from ..config import FhiclizeGenerateConfig
from ..exceptions import FclPreperationError
from ..fhiclutils import fhiclize_known_boardreaders_list, fhiclize_metadata, fhiclize_boot, fhiclize_settings, fhiclize_setup, fhiclize_environment, fhiclize_ranks, generate_run_history

class FclPreparer:

    def __init__(self, fcl_conf_dir: Path, fhiclize_config: Optional[FhiclizeGenerateConfig]=None):
        self._logger = logging.getLogger(__name__)
        self.fcl_conf_dir = fcl_conf_dir
        if not self.fcl_conf_dir.is_dir():
            raise FclPreperationError(f"FCL confdir '{self.fcl_conf_dir}' is not a directory.")
        self.fhiclize_config = fhiclize_config or FhiclizeGenerateConfig(None)
        self._converter_map: Dict[str, Callable[[str], str]] = {'metadata': fhiclize_metadata, 'boot': fhiclize_boot, 'known_boardreaders_list': fhiclize_known_boardreaders_list, 'settings': fhiclize_settings, 'setup': fhiclize_setup, 'environment': fhiclize_environment, 'ranks': fhiclize_ranks}

    def prepare_fcl_for_archive(self, run_dir: Path, tmpdir_path: Path) -> str:
        try:
            shutil.copytree(run_dir, tmpdir_path, dirs_exist_ok=True)
            tmpdir_path.chmod(493)
            for path in tmpdir_path.rglob('*'):
                if path.is_file():
                    path.chmod(420)
            run_number = None
            try:
                run_number = int(run_dir.name)
            except ValueError:
                pass
            for src_path in tmpdir_path.glob('*.txt'):
                basename = src_path.stem
                if self.fhiclize_config.should_convert(basename):
                    converter = self._converter_map.get(basename)
                    if converter:
                        fcl_name = basename + '.fcl'
                        dest_path = tmpdir_path / fcl_name
                        content = src_path.read_text(encoding='utf-8')
                        dest_path.write_text(converter(content), encoding='utf-8')
                        src_path.unlink()
                        self._logger.debug('Converted %s to %s', src_path.name, fcl_name)
                    else:
                        self._logger.warning('No converter found for configured file: %s', basename)
                else:
                    self._logger.debug('Skipping %s (not in fhiclize_generate config)', src_path.name)
            if self.fhiclize_config.should_generate('RunHistory'):
                metadata_txt = run_dir / 'metadata.txt'
                if metadata_txt.exists():
                    metadata_content = metadata_txt.read_text(encoding='utf-8')
                    runhistory_content = generate_run_history(metadata_content, run_number)
                    (tmpdir_path / 'RunHistory.fcl').write_text(runhistory_content, encoding='utf-8')
                    self._logger.debug('Generated RunHistory.fcl from metadata.txt')
                else:
                    self._logger.warning('Cannot generate RunHistory.fcl: metadata.txt not found in run directory')
            schema_src = self.fcl_conf_dir / 'schema.fcl'
            if not schema_src.is_file():
                raise FclPreperationError(f'Schema not found at {schema_src}')
            shutil.copy(schema_src, tmpdir_path)
            return self._resolve_config_name(run_dir)
        except (IOError, shutil.Error) as e:
            raise FclPreperationError(f'Error preparing FCL for archive: {e}') from e

    def prepare_fcl_for_update(self, run_dir: Path, tmpdir_path: Path) -> bool:
        try:
            if not self.fhiclize_config.should_generate('RunHistory2'):
                self._logger.debug('RunHistory2 not in fhiclize_generate config, skipping update')
                return False
            rh2_content = []
            if (metadata_path := (run_dir / 'metadata.txt')).exists():
                for line in metadata_path.read_text(encoding='utf-8').splitlines():
                    match = re.search('^DAQInterface stop time:\\s+(.*)', line)
                    if match:
                        stop_time_value = match.group(1)
                        rh2_content.append(f'DAQInterface_stop_time: "{stop_time_value}"')
                    match = re.search('^DAQInterface start time:\\s+(.*)', line)
                    if match:
                        start_time_value = match.group(1)
                        rh2_content.append(f'DAQInterface_start_time: "{start_time_value}"')
            if not rh2_content:
                self._logger.debug('No stop-time found for run %s, skipping update', run_dir.name)
                return False
            cleaned_lines = [''.join((c if ord(c) < 128 else '.' for c in line)) for line in rh2_content]
            (tmpdir_path / 'RunHistory2.fcl').write_text('\n'.join(cleaned_lines), encoding='utf-8')
            self._logger.debug('Generated RunHistory2.fcl for update')
            schema_src = self.fcl_conf_dir / 'schema.fcl'
            if not schema_src.is_file():
                raise FclPreperationError(f'Schema not found at {schema_src}')
            shutil.copy(schema_src, tmpdir_path)
            return True
        except IOError as e:
            raise FclPreperationError(f'Error preparing FCL for update: {e}') from e

    def _fhiclize_document(self, filepath: Path) -> str:
        fhiclized_lines: List[str] = []
        try:
            for line in filepath.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if (match := re.match('^([^:]+?)\\s*:\\s*(.*)', line)):
                    (key, value) = match.groups()
                    key = re.sub('[\\s()/#.\\-]', '_', key.strip())
                    value = value.strip().strip('\'"').replace('"', '\\"')
                    value = ''.join((c if ord(c) < 128 else '.' for c in value))
                    fhiclized_lines.append(f'{key}: "{value}"')
        except IOError as e:
            raise FclPreperationError(f'Could not FHiCLize {filepath}: {e}') from e
        return '\n'.join(fhiclized_lines)

    def _fhiclize_environment(self, filepath: Path) -> str:
        fhiclized_lines: List[str] = []
        try:
            for line in filepath.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if (match := re.match('^export\\s+([A-Za-z_][A-Za-z0-9_]*)\\s*=\\s*(.*)$', line)):
                    (key, value) = match.groups()
                    value = value.strip().strip('\'"').replace('"', '\\"')
                    value = ''.join((c if ord(c) < 128 else '.' for c in value))
                    fhiclized_lines.append(f'{key}: "{value}"')
        except IOError as e:
            raise FclPreperationError(f'Could not FHiCLize environment file {filepath}: {e}') from e
        return '\n'.join(fhiclized_lines)

    def _fhiclize_tabular(self, filepath: Path) -> str:
        try:
            content = filepath.read_text(encoding='utf-8')
            content = ''.join((c if ord(c) < 128 else '.' for c in content))
            content = content.replace('\\', '\\\\').replace('"', '\\"')
            content = content.replace('\n', '\\n')
            key = filepath.stem
            return f'{key}: "{content}"'
        except IOError as e:
            raise FclPreperationError(f'Could not FHiCLize tabular file {filepath}: {e}') from e

    def _resolve_config_name(self, run_dir: Path) -> str:
        metadata_file = run_dir / 'metadata.txt'
        if metadata_file.exists():
            try:
                for line in metadata_file.read_text(encoding='utf-8').splitlines():
                    if (match := re.match('^Config name:\\s+(.*)', line)):
                        if (name := match.group(1).strip()):
                            return name.replace('/', '_')
            except IOError as e:
                self._logger.warning('Could not read metadata file %s: %s', run_dir, e)
        return 'standard'