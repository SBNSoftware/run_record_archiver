import logging
import re
from typing import Dict, Tuple
DEFAULT_PARAMETER_SPEC = {'metadata.fcl': {'components': 'components', 'configuration': 'config_name', 'projectversion': 'sbndaq_commit_or_version'}}

class BlobValidator:

    def __init__(self, parameter_spec: Dict[str, Dict[str, str]]=None):
        self.parameter_spec = parameter_spec or DEFAULT_PARAMETER_SPEC
        self._logger = logging.getLogger(__name__)

    def unpack_blob(self, blob: str) -> Dict[str, str]:
        files = {}
        pattern = re.compile('#####\\n(.+?):\\n#####\\n([\\s\\S]*?)(?=(?:\\n#####)|(?:\\nEnd of Record))')
        for match in pattern.finditer(blob):
            filename = match.group(1)
            content = match.group(2)
            files[filename] = content
        self._logger.debug('Extracted %d files from blob', len(files))
        return files

    def parse_metadata(self, metadata_content: str, file_spec: Dict[str, str]) -> Tuple[int, Dict[str, str]]:
        results = {}
        error_count = 0
        for (param_name, fhicl_key) in file_spec.items():
            pattern = f'{fhicl_key}:\\s+(.+)'
            matches = re.findall(pattern, metadata_content)
            if not matches:
                results[param_name] = f"Error: no matches for parameter '{fhicl_key}'"
                error_count += 1
                continue
            if len(matches) > 1:
                results[param_name] = f"Error: multiple matches for parameter '{fhicl_key}'"
                error_count += 1
                continue
            value = matches[0].replace('"', '').strip()
            results[param_name] = value
        return (error_count, results)

    def validate_blob(self, blob: str, run_number: int) -> Tuple[int, Dict[str, str]]:
        self._logger.debug('Validating blob for run %d', run_number)
        try:
            files = self.unpack_blob(blob)
        except Exception as e:
            self._logger.error('Failed to unpack blob for run %d: %s', run_number, e)
            return (1, {'error': f'Failed to unpack blob: {e}'})
        if not files:
            self._logger.warning('No files found in blob for run %d', run_number)
            return (1, {'error': 'No files found in blob'})
        all_results = {}
        total_errors = 0
        for (file_name, file_spec) in self.parameter_spec.items():
            if file_name not in files:
                self._logger.warning("Required file '%s' not found in blob for run %d", file_name, run_number)
                for param_name in file_spec.keys():
                    all_results[param_name] = f"Error: file '{file_name}' not found"
                total_errors += len(file_spec)
                continue
            (error_count, results) = self.parse_metadata(files[file_name], file_spec)
            total_errors += error_count
            all_results.update(results)
        if total_errors == 0:
            self._logger.info('✓ Blob validation passed for run %d: %s', run_number, all_results)
        else:
            self._logger.warning('✗ Blob validation found %d errors for run %d: %s', total_errors, run_number, all_results)
        return (total_errors, all_results)