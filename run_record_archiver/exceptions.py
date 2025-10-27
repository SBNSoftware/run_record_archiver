import logging
from typing import Optional

class ArchiverError(Exception):

    def __init__(self, message: str, stage: Optional[str]=None, run_number: Optional[int]=None, context: Optional[dict]=None):
        self.stage = stage
        self.run_number = run_number
        self.context = context or {}
        parts = []
        if stage:
            parts.append(f'[{stage}]')
        if run_number is not None:
            parts.append(f'[Run {run_number}]')
        parts.append(message)
        full_message = ' '.join(parts)
        super().__init__(full_message)
        logger = logging.getLogger(__name__)
        logger.debug('Exception raised: %s - Stage: %s, Run: %s, Context: %s', self.__class__.__name__, stage, run_number, self.context)

    def get_summary(self) -> str:
        summary = f'{self.__class__.__name__}: {str(self)}'
        if self.context:
            context_str = ', '.join((f'{k}={v}' for (k, v) in self.context.items()))
            summary += f' | Context: {context_str}'
        return summary

class ConfigurationError(ArchiverError):
    pass

class ArtdaqDBError(ArchiverError):
    pass

class UconDBError(ArchiverError):
    pass

class FclPreperationError(ArchiverError):
    pass

class BlobCreationError(ArchiverError):
    pass

class ReportingError(ArchiverError):
    pass

class LockExistsError(ArchiverError):
    pass

class VerificationError(ArchiverError):
    pass

class FuzzSkipError(ArchiverError):
    pass