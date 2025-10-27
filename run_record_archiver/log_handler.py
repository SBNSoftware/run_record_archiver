import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

class SizeAndTimeRotatingFileHandler(RotatingFileHandler):

    def __init__(self, filename: str, mode: str='a', max_bytes: int=0, backup_count: int=0, encoding: Optional[str]=None, delay: bool=False, max_age_seconds: Optional[int]=None):
        super().__init__(filename, mode, max_bytes, backup_count, encoding, delay)
        self.max_age_seconds = max_age_seconds
        self._log_file_created_time: Optional[float] = None
        if os.path.exists(filename):
            self._log_file_created_time = os.path.getctime(filename)

    def shouldRollover(self, record: logging.LogRecord) -> bool:
        if super().shouldRollover(record):
            return True
        if self.max_age_seconds is not None:
            if self._log_file_created_time is None and os.path.exists(self.baseFilename):
                self._log_file_created_time = os.path.getctime(self.baseFilename)
            if self._log_file_created_time is not None:
                current_time = time.time()
                file_age = current_time - self._log_file_created_time
                if file_age >= self.max_age_seconds:
                    return True
        return False

    def doRollover(self):
        super().doRollover()
        if os.path.exists(self.baseFilename):
            self._log_file_created_time = os.path.getctime(self.baseFilename)
        else:
            self._log_file_created_time = None

    def emit(self, record: logging.LogRecord):
        if self._log_file_created_time is None and self.stream is not None:
            if os.path.exists(self.baseFilename):
                self._log_file_created_time = os.path.getctime(self.baseFilename)
        super().emit(record)