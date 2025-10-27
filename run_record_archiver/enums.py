from enum import Enum, IntEnum

class Stage(str, Enum):
    IMPORT = 'Import'
    MIGRATION = 'Migration'
    RECOVERY_IMPORT = 'Recovery-Import'
    RECOVERY_MIGRATION = 'Recovery-Migration'
    REPORT = 'Report'
    VALIDATION = 'Validation'

class ExecutionMode(str, Enum):
    FULL_PIPELINE = 'full_pipeline'
    IMPORT_ONLY = 'import_only'
    MIGRATE_ONLY = 'migrate_only'
    RETRY_FAILED_IMPORT = 'retry_failed_import'
    RETRY_FAILED_MIGRATE = 'retry_failed_migrate'
    REPORT_STATUS = 'report_status'
    RECOVER_IMPORT_STATE = 'recover_import_state'
    RECOVER_MIGRATE_STATE = 'recover_migrate_state'

class ExitCode(IntEnum):
    SUCCESS = 0
    ERROR = 1
    UNEXPECTED_ERROR = 2
    INTERRUPTED = 130

class LogLevel(str, Enum):
    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'
    CRITICAL = 'CRITICAL'

class DatabaseType(str, Enum):
    MONGODB = 'mongodb'
    FILESYSTEMDB = 'filesystem'

class SignalType(IntEnum):
    SIGINT = 2
    SIGTERM = 15

class FuzzMode(str, Enum):
    SKIP = 'skip'
    ERROR = 'error'
    NONE = 'none'