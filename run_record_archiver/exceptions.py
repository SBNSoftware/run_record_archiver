class ArchiverError(Exception):
    pass


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
