import logging
import time
from pathlib import Path
from typing import List

from ..exceptions import BlobCreationError


class BlobCreator:
    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

    def create_blob_from_directory(self, run_number: int, source_dir: Path) -> str:
        self._logger.debug("Creating blob for run %d from '%s'.", run_number, source_dir)
        try:
            files: List[Path] = sorted(
                [p for p in source_dir.rglob("*") if p.is_file()]
            )
            if not files:
                raise BlobCreationError(
                    f"No config files found in {source_dir} for run {run_number}."
                )

            timestamp = time.strftime("%b %d %H:%M", time.gmtime()) + " UTC"
            header = (
                f"Start of Record\nRun Number: {run_number}\nPacked on {timestamp}\n"
            )
            footer = (
                f"\nEnd of Record\nRun Number: {run_number}\nPacked on {timestamp}\n"
            )

            content_parts = [header]
            for file_path in files:
                relative_path = file_path.relative_to(source_dir)
                content_parts.append(f"\n#####\n{relative_path}:\n#####\n")
                try:
                    content_parts.append(file_path.read_text(encoding="utf-8"))
                except UnicodeDecodeError:
                    self._logger.warning(
                        "File '%s' not UTF-8, reading as binary.", file_path
                    )
                    content_parts.append(
                        file_path.read_bytes().decode("ascii", "ignore")
                    )
            content_parts.append(footer)
            return "".join(content_parts)
        except Exception as e:
            raise BlobCreationError(
                f"Error creating blob for run {run_number}: {e}"
            ) from e
