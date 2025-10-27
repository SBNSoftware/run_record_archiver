import locale
import logging
import re
import time
from pathlib import Path
from typing import Dict, List
from ..exceptions import BlobCreationError

class BlobCreator:

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

    def create_blob_from_directory(self, run_number: int, source_dir: Path) -> str:
        self._logger.debug("Creating blob for run %d from '%s'.", run_number, source_dir)
        try:
            all_files: List[Path] = [p for p in source_dir.rglob('*') if p.is_file()]
            if not all_files:
                raise BlobCreationError(f'No config files found in {source_dir} for run {run_number}.')
            end_files_order = ['boot.fcl', 'known_boardreaders_list.fcl', 'setup.fcl', 'environment.fcl', 'metadata.fcl', 'settings.fcl', 'ranks.fcl', 'RunHistory.fcl', 'RunHistory2.fcl']
            file_map = {p.name.lower(): p for p in all_files}
            end_files = []
            for end_file in end_files_order:
                if end_file.lower() in file_map:
                    end_files.append(file_map[end_file.lower()])
                    del file_map[end_file.lower()]
            regular_files = sorted(file_map.values(), key=lambda p: p.name.lower())
            files = regular_files + end_files
            old_locale = locale.setlocale(locale.LC_TIME)
            try:
                locale.setlocale(locale.LC_TIME, 'C')
                timestamp = time.strftime('%b %d %H:%M', time.gmtime()) + ' UTC'
            finally:
                locale.setlocale(locale.LC_TIME, old_locale)
            header = f'Start of Record\nRun Number: {run_number}\nPacked on {timestamp}\n'
            footer = f'\nEnd of Record\nRun Number: {run_number}\nPacked on {timestamp}\n'
            content_parts = [header]
            for file_path in files:
                filename = file_path.name
                content_parts.append(f'\n#####\n{filename}:\n#####\n')
                try:
                    content_parts.append(file_path.read_text(encoding='utf-8'))
                except UnicodeDecodeError:
                    self._logger.warning("File '%s' not UTF-8, reading as binary.", file_path)
                    content_parts.append(file_path.read_bytes().decode('ascii', 'ignore'))
            content_parts.append(footer)
            return ''.join(content_parts)
        except Exception as e:
            raise BlobCreationError(f'Error creating blob for run {run_number}: {e}') from e

    def extract_files_from_blob(self, blob: str, output_dir: Path) -> Dict[str, Path]:
        self._logger.debug("Extracting files from blob to '%s'.", output_dir)
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            pattern = '\\n#####\\n(.+?):\\n#####\\n'
            matches = list(re.finditer(pattern, blob))
            if not matches:
                raise BlobCreationError('No file markers found in blob')
            extracted_files: Dict[str, Path] = {}
            for (i, match) in enumerate(matches):
                filename = match.group(1)
                content_start = match.end()
                if i + 1 < len(matches):
                    content_end = matches[i + 1].start()
                else:
                    footer_match = re.search('\\nEnd of Record\\n', blob[content_start:])
                    if footer_match:
                        content_end = content_start + footer_match.start()
                    else:
                        content_end = len(blob)
                content = blob[content_start:content_end]
                file_path = output_dir / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding='utf-8')
                extracted_files[filename] = file_path
                self._logger.debug('Extracted file: %s', filename)
            self._logger.info('Extracted %d files from blob', len(extracted_files))
            return extracted_files
        except Exception as e:
            raise BlobCreationError(f'Error extracting files from blob: {e}') from e