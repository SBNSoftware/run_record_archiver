import fcntl
import os
from pathlib import Path
from ..exceptions import LockExistsError

class FileLock:

    def __init__(self, lock_file: Path):
        self.lock_file = lock_file
        self.lock_file_handle = None
        self.pid = os.getpid()

    def __enter__(self):
        try:
            self.lock_file.parent.mkdir(parents=True, exist_ok=True)
            self.lock_file_handle = open(self.lock_file, 'w', encoding='utf-8')
            fcntl.flock(self.lock_file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_file_handle.write(f'{self.pid}\n')
            self.lock_file_handle.flush()
            return self
        except (IOError, BlockingIOError) as exc:
            if self.lock_file_handle:
                self.lock_file_handle.close()
            raise LockExistsError(f"Another process may be running. Lock file '{self.lock_file}' is held.") from exc

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.lock_file_handle:
            fcntl.flock(self.lock_file_handle, fcntl.LOCK_UN)
            self.lock_file_handle.close()
            self.lock_file_handle = None

    def is_lock_file_valid(self) -> bool:
        try:
            if not self.lock_file.exists():
                return False
            with open(self.lock_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    return False
                try:
                    file_pid = int(content)
                    return file_pid == self.pid
                except ValueError:
                    return False
        except (IOError, PermissionError):
            return False

    def get_pid(self) -> int:
        return self.pid