# Core Modules Reference

This document provides comprehensive documentation for the core modules of the Run Record Archiver. These modules form the foundation of the application, providing configuration management, exception handling, constants, type safety, utility functions, base classes, decorators, and custom logging.

## Table of Contents

1. [config.py - Configuration Management](#configpy---configuration-management)
2. [exceptions.py - Exception Hierarchy](#exceptionspy---exception-hierarchy)
3. [constants.py - Application Constants](#constantspy---application-constants)
4. [enums.py - Type-Safe Enumerations](#enumspy---type-safe-enumerations)
5. [utils.py - Utility Functions](#utilspy---utility-functions)
6. [base_stage.py - Abstract Base Class for Pipeline Stages](#base_stagepy---abstract-base-class-for-pipeline-stages)
7. [decorators.py - Retry Decorators](#decoratorspy---retry-decorators)
8. [log_handler.py - Custom Logging](#log_handlerpy---custom-logging)

---

## config.py - Configuration Management

**Purpose**: Provides a robust configuration management system with YAML file parsing, environment variable expansion, parameter reference resolution, and validation.

**Location**: `~/run_record_archiver/dist/run_record_archiver/config.py`

### Key Classes

#### ConfigExpander

**Purpose**: Handles environment variable expansion and parameter reference resolution in configuration values.

**Features**:
- Expands environment variables with syntax `${VAR_NAME}` or `${VAR_NAME:-default}`
- Resolves parameter references with syntax `${section.param}` or `${param}` (relative)
- Supports nested references with recursive expansion
- Detects and prevents circular references
- Handles complex nested structures (dicts, lists)

**Environment Variable Pattern**:
```python
ENV_VAR_PATTERN = re.compile(r'\$\{([A-Z][A-Z0-9_]*)(:-([^}]*))?\}')
```
- Matches uppercase environment variables
- Supports default values with `:-` separator

**Parameter Reference Pattern**:
```python
PARAM_REF_PATTERN = re.compile(r'\$\{([a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*)\}')
```
- Matches lowercase parameter references
- Supports dotted paths (e.g., `artdaq_db.database_uri`)

**Methods**:

```python
@classmethod
def expand_config(cls, config_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main entry point for config expansion.
    First expands environment variables, then resolves parameter references.
    
    Returns:
        Fully expanded configuration dictionary
    """
```

**Usage Example**:
```yaml
# config.yaml
app:
  work_dir: "${WORK_DIR:-/tmp/archiver}"
  log_file: "${work_dir}/archiver.log"

artdaq_db:
  database_uri: "mongodb://${MONGO_HOST}:${MONGO_PORT}/artdaq_db"
```

After expansion:
```python
# If WORK_DIR="/data/archiver", MONGO_HOST="localhost", MONGO_PORT="27017"
{
  "app": {
    "work_dir": "/data/archiver",
    "log_file": "/data/archiver/archiver.log"
  },
  "artdaq_db": {
    "database_uri": "mongodb://localhost:27017/artdaq_db"
  }
}
```

---

#### AppConfig

**Purpose**: Configuration for application-level settings (work directory, state files, batch processing).

**Attributes**:
```python
work_dir: Path                      # Working directory for temp files and state
import_state_file: Path             # Import stage state tracking
import_failure_log: Path            # Failed import runs log
migrate_state_file: Path            # Migration stage state tracking
migrate_failure_log: Path           # Failed migration runs log
lock_file: Path                     # File-based lock for single instance
batch_size: int                     # Number of runs per batch (default: 5)
parallel_workers: int               # ThreadPoolExecutor workers (default: 2)
run_process_retries: int            # Retry attempts per run (default: 2)
retry_delay_seconds: int            # Delay between retries (default: 3)
log_level: str                      # Logging level (default: "INFO")
log_file: Optional[Path]            # Log file path (optional)
```

**Defaults**: All paths default to subdirectories/files within `work_dir`.

---

#### AppFuzzConfig

**Purpose**: Configuration for fuzzing/testing features to simulate failures.

**Attributes**:
```python
random_skip_percent: int            # Percentage of runs to skip (0-100, default: 0)
random_skip_retry: bool             # If true, skipped runs fail permanently (default: False)
random_error_percent: int           # Percentage of runs to randomly fail (0-100, default: 0)
random_error_retry: bool            # If true, errored runs fail permanently (default: False)
```

**Usage**: Enable failure simulation for testing retry logic and failure handling.

---

#### SourceFilesConfig

**Purpose**: Configuration for source filesystem paths.

**Attributes**:
```python
run_records_dir: Path               # REQUIRED: Root directory containing run records
```

**Validation**: Raises `ConfigurationError` if `run_records_dir` is missing.

---

#### ArtdaqDBConfig

**Purpose**: Configuration for ArtdaqDB (intermediate storage layer).

**Attributes**:
```python
use_tools: bool                     # Use CLI tools (bulkloader/bulkdownloader) instead of API (default: False)
remote_host: Optional[str]          # Remote host for CLI tools via SSH (optional)
database_uri: str                   # REQUIRED: Database connection URI (MongoDB or FilesystemDB)
fcl_conf_dir: Path                  # REQUIRED: FHiCL configuration directory
```

**Database URI Examples**:
```python
# MongoDB
"mongodb://localhost:27017/artdaq_database"

# FilesystemDB
"filesystemdb:///path/to/database"
```

**Important**: The `database_uri` is used exactly as configured (no automatic suffix appending).

---

#### UconDBConfig

**Purpose**: Configuration for UconDB (final archive destination).

**Attributes**:
```python
timeout_seconds: int                # HTTP request timeout (default: 10)
server_url: str                     # REQUIRED: UconDB server URL
folder_name: str                    # REQUIRED: Target folder name
object_name: str                    # REQUIRED: Object name for archives
writer_user: str                    # REQUIRED: Authentication username
writer_password: str                # REQUIRED: Authentication password
```

**Validation**: Raises `ConfigurationError` if any required field is missing.

---

#### EmailConfig

**Purpose**: Email notification configuration.

**Attributes**:
```python
enabled: bool                       # Enable email notifications (default: False)
recipient_email: Optional[str]      # Recipient address
sender_email: Optional[str]         # Sender address
smtp_host: Optional[str]            # SMTP server hostname
smtp_port: int                      # SMTP server port (default: 25)
smtp_use_tls: bool                  # Use TLS encryption (default: False)
smtp_user: Optional[str]            # SMTP authentication username (optional)
smtp_password: Optional[str]        # SMTP authentication password (optional)
```

**Validation**: When `enabled=True`, requires `recipient_email`, `sender_email`, and `smtp_host`.

---

#### SlackConfig

**Purpose**: Slack notification configuration.

**Attributes**:
```python
enabled: bool                       # Enable Slack notifications (default: False)
bot_token: Optional[str]            # Slack bot token
channel: Optional[str]              # Target channel ID or name
mention_users: Optional[str]        # Users to mention in notifications (optional)
```

**Validation**: When `enabled=True`, requires `bot_token` and `channel`.

---

#### ReportingConfig

**Purpose**: Container for notification configurations.

**Attributes**:
```python
email: EmailConfig                  # Email notification settings
slack: SlackConfig                  # Slack notification settings
```

**Legacy Support**: Supports deprecated top-level email config for backward compatibility.

---

#### CarbonConfig

**Purpose**: Carbon/Graphite metrics reporting configuration.

**Attributes**:
```python
enabled: bool                       # Enable metrics reporting (default: False)
host: Optional[str]                 # Carbon server hostname
port: int                           # Carbon server port (default: 2003)
metric_prefix: Optional[str]        # Metric name prefix
```

**Validation**: When `enabled=True`, requires `host` and `metric_prefix`.

---

#### FhiclizeGenerateConfig

**Purpose**: Controls which files are converted/generated during FHiCL preparation.

**Known Converters**:
```python
KNOWN_CONVERTERS = {
    'boot', 'metadata', 'known_boardreaders_list',
    'settings', 'setup', 'environment', 'ranks'
}
```

**Known Generators**:
```python
KNOWN_GENERATORS = {'RunHistory', 'RunHistory2'}
```

**Attributes**:
```python
file_list: List[str]                # List of files to convert/generate
converters: Set[str]                # Subset that are converters
generators: Set[str]                # Subset that are generators
```

**Configuration Formats**:

1. **None (default)** - Process all known converters and generators:
```yaml
fhiclize_generate: null
```

2. **List format** - Process specific files:
```yaml
fhiclize_generate:
  - boot
  - metadata
  - RunHistory
```

3. **Dict format** - Process files in `files` key:
```yaml
fhiclize_generate:
  files:
    - boot
    - metadata
    - RunHistory
```

**Methods**:

```python
def should_convert(self, filename: str) -> bool:
    """Check if file should be converted to .fcl format."""
    
def should_generate(self, filename: str) -> bool:
    """Check if file should be generated from other data."""
```

**Validation**: Raises `ConfigurationError` if unknown file types are specified.

---

#### Config

**Purpose**: Top-level configuration container.

**Attributes**:
```python
app: AppConfig                      # Application settings
app_fuzz: AppFuzzConfig             # Fuzzing/testing settings
source_files: SourceFilesConfig     # Source filesystem paths
artdaq_db: ArtdaqDBConfig           # ArtdaqDB configuration
ucon_db: UconDBConfig               # UconDB configuration
reporting: ReportingConfig          # Notification settings
carbon: CarbonConfig                # Metrics reporting settings
fhiclize_generate: FhiclizeGenerateConfig  # FHiCL file processing
```

**Static Methods**:

```python
@staticmethod
def from_file(path: str) -> 'Config':
    """
    Load configuration from YAML file.
    
    Args:
        path: Path to configuration file
        
    Returns:
        Fully expanded and validated Config object
        
    Raises:
        ConfigurationError: If file not found, invalid YAML, or validation fails
    """
```

**Usage Example**:
```python
from run_record_archiver.config import Config

# Load configuration
config = Config.from_file('/path/to/config.yaml')

# Access nested configuration
work_dir = config.app.work_dir
db_uri = config.artdaq_db.database_uri
ucondb_url = config.ucon_db.server_url

# Check feature flags
if config.reporting.email.enabled:
    # Send email notification
    pass

if config.artdaq_db.use_tools:
    # Use CLI tools instead of API
    pass
```

---

## exceptions.py - Exception Hierarchy

**Purpose**: Provides a comprehensive exception hierarchy for error handling with contextual information.

**Location**: `~/run_record_archiver/dist/run_record_archiver/exceptions.py`

### Exception Hierarchy

```
Exception
└── ArchiverError (base class)
    ├── ConfigurationError
    ├── ArtdaqDBError
    ├── UconDBError
    ├── FclPreperationError
    ├── BlobCreationError
    ├── ReportingError
    ├── LockExistsError
    ├── VerificationError
    └── FuzzSkipError
```

---

### ArchiverError (Base Class)

**Purpose**: Base exception for all archiver-specific errors with contextual metadata.

**Constructor**:
```python
def __init__(
    self,
    message: str,
    stage: Optional[str] = None,
    run_number: Optional[int] = None,
    context: Optional[dict] = None
):
    """
    Args:
        message: Error description
        stage: Pipeline stage where error occurred (e.g., "Import", "Migration")
        run_number: Run number being processed when error occurred
        context: Additional contextual information as key-value pairs
    """
```

**Attributes**:
```python
stage: Optional[str]                # Pipeline stage
run_number: Optional[int]           # Run number
context: dict                       # Additional context
```

**Methods**:

```python
def get_summary(self) -> str:
    """
    Generate concise error summary including context.
    
    Returns:
        Formatted summary string with exception type, message, and context
        
    Example:
        "ArtdaqDBError: [Import] [Run 12345] Connection failed | Context: host=localhost, port=27017"
    """
```

**Message Formatting**:
The exception automatically formats the error message with stage and run number:
```python
# Input
ArchiverError("Database connection failed", stage="Import", run_number=12345)

# Formatted message
"[Import] [Run 12345] Database connection failed"
```

**Debug Logging**:
Every exception logs debug information when raised:
```python
logger.debug(
    'Exception raised: %s - Stage: %s, Run: %s, Context: %s',
    self.__class__.__name__, stage, run_number, self.context
)
```

---

### Exception Types

#### ConfigurationError

**Purpose**: Configuration-related errors (invalid YAML, missing required fields, validation failures).

**When to Use**:
- Configuration file not found
- Invalid YAML syntax
- Missing required configuration parameters
- Invalid configuration values
- Circular reference in parameter expansion

**Example**:
```python
from run_record_archiver.exceptions import ConfigurationError

raise ConfigurationError(
    "Missing required field: 'database_uri'",
    context={'section': 'artdaq_db'}
)
```

---

#### ArtdaqDBError

**Purpose**: Errors related to ArtdaqDB operations.

**When to Use**:
- Database connection failures
- Query errors
- Insert/update failures
- Export failures
- CLI tool errors (bulkloader, bulkdownloader)

**Example**:
```python
from run_record_archiver.exceptions import ArtdaqDBError
from run_record_archiver.enums import Stage

raise ArtdaqDBError(
    "Failed to insert run configuration",
    stage=Stage.IMPORT,
    run_number=12345,
    context={'database_uri': db_uri, 'config_name': config_name}
)
```

---

#### UconDBError

**Purpose**: Errors related to UconDB operations.

**When to Use**:
- HTTP request failures
- Authentication errors
- Upload failures
- MD5 verification failures
- Server-side errors

**Example**:
```python
from run_record_archiver.exceptions import UconDBError
from run_record_archiver.enums import Stage

raise UconDBError(
    "Upload failed with status 500",
    stage=Stage.MIGRATION,
    run_number=12345,
    context={'server_url': url, 'status_code': 500}
)
```

---

#### FclPreperationError

**Purpose**: Errors during FHiCL file preparation/transformation.

**When to Use**:
- File parsing errors
- Conversion failures
- Generator errors
- Missing source files

**Example**:
```python
from run_record_archiver.exceptions import FclPreperationError

raise FclPreperationError(
    "Failed to convert boot.txt to boot.fcl",
    stage=Stage.IMPORT,
    run_number=12345,
    context={'source_file': source_path}
)
```

---

#### BlobCreationError

**Purpose**: Errors during blob creation (concatenating FHiCL files).

**When to Use**:
- File reading failures
- Concatenation errors
- MD5 hash computation failures

**Example**:
```python
from run_record_archiver.exceptions import BlobCreationError

raise BlobCreationError(
    "Failed to read exported FHiCL file",
    stage=Stage.MIGRATION,
    run_number=12345,
    context={'file_path': fcl_path}
)
```

---

#### ReportingError

**Purpose**: Errors during notification delivery (email, Slack).

**When to Use**:
- SMTP connection failures
- Email send failures
- Slack API errors

**Example**:
```python
from run_record_archiver.exceptions import ReportingError

raise ReportingError(
    "Failed to send email notification",
    context={'smtp_host': smtp_host, 'error': str(e)}
)
```

---

#### LockExistsError

**Purpose**: File lock already exists (another instance running).

**When to Use**:
- Lock file acquisition fails
- Concurrent execution detected

**Example**:
```python
from run_record_archiver.exceptions import LockExistsError

raise LockExistsError(
    "Another archiver instance is running",
    context={'lock_file': lock_path, 'pid': existing_pid}
)
```

---

#### VerificationError

**Purpose**: Data integrity verification failures.

**When to Use**:
- MD5 hash mismatches
- Data corruption detected
- Integrity check failures

**Example**:
```python
from run_record_archiver.exceptions import VerificationError

raise VerificationError(
    "MD5 hash mismatch after upload",
    stage=Stage.MIGRATION,
    run_number=12345,
    context={'expected': expected_md5, 'actual': actual_md5}
)
```

---

#### FuzzSkipError

**Purpose**: Indicates a run should be permanently failed (used in testing/fuzzing).

**When to Use**:
- Fuzzing mode with `random_skip_retry=True` or `random_error_retry=True`
- Simulating permanent failures for testing

**Special Handling**:
This exception is caught separately from other `ArchiverError` types and prevents retry attempts.

**Example**:
```python
from run_record_archiver.exceptions import FuzzSkipError

if random.random() < skip_probability:
    raise FuzzSkipError(
        "Run permanently failed (fuzz skip)",
        stage=Stage.IMPORT,
        run_number=12345
    )
```

---

### Error Handling Patterns

#### Pattern 1: Catch and Re-raise with Context

```python
from run_record_archiver.exceptions import ArtdaqDBError
from run_record_archiver.enums import Stage

try:
    result = database.insert(config)
except Exception as e:
    raise ArtdaqDBError(
        f"Database insert failed: {e}",
        stage=Stage.IMPORT,
        run_number=run_number,
        context={'config_name': config_name}
    ) from e
```

#### Pattern 2: Use in Retry Logic

```python
from run_record_archiver.exceptions import UconDBError, FuzzSkipError

try:
    upload_to_ucondb(data)
except FuzzSkipError:
    # Don't retry - permanent failure
    logger.error("Run permanently failed (fuzz skip)")
    return False
except UconDBError as e:
    # Retry on UconDBError
    logger.warning("Upload failed, will retry: %s", e)
    raise
```

#### Pattern 3: Generate Error Summary

```python
from run_record_archiver.exceptions import ArchiverError

try:
    process_run(run_number)
except ArchiverError as e:
    # Log detailed error with context
    logger.error(e.get_summary())
    
    # Send notification with context
    send_notification(
        subject=f"Run {e.run_number} failed",
        body=e.get_summary()
    )
```

---

## constants.py - Application Constants

**Purpose**: Centralized constants for timeouts, retries, limits, and exit codes to eliminate magic numbers.

**Location**: `~/run_record_archiver/dist/run_record_archiver/constants.py`

### Constants Reference

#### Timeout Constants

```python
DEFAULT_UCONDB_TIMEOUT_SECONDS = 30
# Default timeout for UconDB HTTP requests
# Used when config.ucon_db.timeout_seconds is not specified

EMAIL_SMTP_TIMEOUT_SECONDS = 10
# SMTP connection and send timeout
# Prevents hanging on unresponsive mail servers

PROCESS_RUNNER_TIMEOUT_SECONDS = 300
# Default timeout for external process execution
# Applies to bulkloader, bulkdownloader, SSH transfers (5 minutes)

LOCK_MONITOR_JOIN_TIMEOUT_SECONDS = 2.0
# Timeout for joining lock monitor thread during shutdown
# Short timeout to avoid delaying shutdown

LOCK_MONITOR_POLL_INTERVAL_SECONDS = 0.1
# Polling interval for lock file monitoring thread
# Balances responsiveness and CPU usage
```

---

#### Retry Constants

```python
DEFAULT_RUN_PROCESS_RETRIES = 2
# Default number of retry attempts per run
# Total attempts = retries + 1 (initial attempt)
```

---

#### Signal Handling Constants

```python
SIGINT_IMMEDIATE_SHUTDOWN_COUNT = 3
# Number of SIGINT signals within time window to trigger immediate shutdown
# First SIGINT: graceful shutdown
# Second SIGINT: warn user
# Third+ SIGINT: immediate exit

SIGINT_TIME_WINDOW_SECONDS = 2.0
# Time window for counting rapid SIGINT signals
# Resets if signals are spaced out
```

---

#### Log Rotation Constants

```python
LOG_FILE_MAX_BYTES = 500 * 1024 * 1024
# Maximum log file size before rotation (500 MB)
# Prevents unbounded log file growth

LOG_FILE_MAX_AGE_SECONDS = 14 * 24 * 60 * 60
# Maximum log file age before rotation (14 days)
# Ensures regular rotation even for low-activity systems

LOG_FILE_BACKUP_COUNT = 5
# Number of rotated log files to keep
# Total log storage ≈ 500 MB × 6 = 3 GB
```

---

#### Progress Reporting Constants

```python
PROGRESS_REPORT_INTERVAL = 10
# Report progress every N runs processed
# Balances visibility and log noise

PREVIEW_LIST_LIMIT = 10
# Maximum number of items to show in preview lists
# Used for logging "first N runs to process"
```

---

#### Exit Code Constants

```python
EXIT_CODE_SUCCESS = 0
# Successful execution
# All runs processed successfully

EXIT_CODE_ERROR = 1
# Known error occurred (ArchiverError, LockExistsError)
# Error was handled and logged appropriately

EXIT_CODE_UNEXPECTED_ERROR = 2
# Unexpected/unhandled exception
# Indicates a bug or unforeseen condition

EXIT_CODE_INTERRUPTED = 130
# Process interrupted by signal (SIGINT/SIGTERM)
# Standard Unix exit code for SIGINT (128 + 2)
```

---

#### Numeric Constants

```python
ZERO = 0
# Semantic zero for comparisons and initial values
# More readable than bare 0 in some contexts

ONE = 1
# Semantic one for comparisons and increments
# More readable than bare 1 in some contexts

MAX_DUPLICATE_CONFIG_ENTRIES = 1
# Maximum allowed duplicate configuration entries in artdaqDB
# Used for validation and error detection
```

---

### Usage Guidelines

#### DO: Use Named Constants

```python
# GOOD
from run_record_archiver.constants import EXIT_CODE_SUCCESS, EXIT_CODE_ERROR

if successful:
    return EXIT_CODE_SUCCESS
else:
    return EXIT_CODE_ERROR
```

```python
# BAD - Magic numbers
if successful:
    return 0
else:
    return 1
```

---

#### DO: Use Constants for Configuration Defaults

```python
# GOOD
from run_record_archiver.constants import DEFAULT_UCONDB_TIMEOUT_SECONDS

timeout = config.get('timeout_seconds', DEFAULT_UCONDB_TIMEOUT_SECONDS)
```

```python
# BAD - Magic number
timeout = config.get('timeout_seconds', 30)
```

---

#### DO: Use Constants in Conditionals

```python
# GOOD
from run_record_archiver.constants import SIGINT_IMMEDIATE_SHUTDOWN_COUNT

if sigint_count >= SIGINT_IMMEDIATE_SHUTDOWN_COUNT:
    logger.critical("Immediate shutdown requested")
    sys.exit(EXIT_CODE_INTERRUPTED)
```

```python
# BAD - Magic number
if sigint_count >= 3:
    logger.critical("Immediate shutdown requested")
    sys.exit(130)
```

---

## enums.py - Type-Safe Enumerations

**Purpose**: Provides type-safe enumerations to replace string literals and magic numbers with explicit types.

**Location**: `~/run_record_archiver/dist/run_record_archiver/enums.py`

### Enum Types

#### Stage

**Purpose**: Represents pipeline stages for error reporting and logging.

```python
class Stage(str, Enum):
    IMPORT = 'Import'
    MIGRATION = 'Migration'
    RECOVERY_IMPORT = 'Recovery-Import'
    RECOVERY_MIGRATION = 'Recovery-Migration'
    REPORT = 'Report'
    VALIDATION = 'Validation'
```

**Usage**:
```python
from run_record_archiver.enums import Stage

raise ArtdaqDBError(
    "Database connection failed",
    stage=Stage.IMPORT,  # Type-safe, autocomplete-friendly
    run_number=12345
)

# String representation
str(Stage.IMPORT)  # "Import"
```

---

#### ExecutionMode

**Purpose**: Represents archiver execution modes (mutually exclusive command-line options).

```python
class ExecutionMode(str, Enum):
    FULL_PIPELINE = 'full_pipeline'
    IMPORT_ONLY = 'import_only'
    MIGRATE_ONLY = 'migrate_only'
    RETRY_FAILED_IMPORT = 'retry_failed_import'
    RETRY_FAILED_MIGRATE = 'retry_failed_migrate'
    REPORT_STATUS = 'report_status'
    RECOVER_IMPORT_STATE = 'recover_import_state'
    RECOVER_MIGRATE_STATE = 'recover_migrate_state'
```

**Usage**:
```python
from run_record_archiver.enums import ExecutionMode

mode = ExecutionMode.IMPORT_ONLY

if mode == ExecutionMode.FULL_PIPELINE:
    run_import_stage()
    run_migration_stage()
elif mode == ExecutionMode.IMPORT_ONLY:
    run_import_stage()
elif mode == ExecutionMode.MIGRATE_ONLY:
    run_migration_stage()
```

**Benefits**:
- IDE autocomplete for valid modes
- Type checking catches typos
- Explicit documentation of valid modes

---

#### ExitCode

**Purpose**: Standardized exit codes for process termination.

```python
class ExitCode(IntEnum):
    SUCCESS = 0
    ERROR = 1
    UNEXPECTED_ERROR = 2
    INTERRUPTED = 130
```

**Usage**:
```python
from run_record_archiver.enums import ExitCode
import sys

try:
    run_archiver()
    sys.exit(ExitCode.SUCCESS)
except ArchiverError as e:
    logger.error("Known error: %s", e)
    sys.exit(ExitCode.ERROR)
except Exception as e:
    logger.exception("Unexpected error: %s", e)
    sys.exit(ExitCode.UNEXPECTED_ERROR)
```

**Shell Integration**:
```bash
#!/bin/bash
./run_archiver.sh config.yaml
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "Success"
elif [ $EXIT_CODE -eq 1 ]; then
    echo "Known error occurred"
elif [ $EXIT_CODE -eq 2 ]; then
    echo "Unexpected error - check logs"
elif [ $EXIT_CODE -eq 130 ]; then
    echo "Process was interrupted"
fi
```

---

#### LogLevel

**Purpose**: Standard logging levels (matches Python logging module).

```python
class LogLevel(str, Enum):
    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'
    CRITICAL = 'CRITICAL'
```

**Usage**:
```python
from run_record_archiver.enums import LogLevel
import logging

log_level = config.app.log_level
logging.basicConfig(level=getattr(logging, log_level))

# Validation
if log_level not in [level.value for level in LogLevel]:
    raise ConfigurationError(f"Invalid log level: {log_level}")
```

---

#### DatabaseType

**Purpose**: Supported database backends for ArtdaqDB.

```python
class DatabaseType(str, Enum):
    MONGODB = 'mongodb'
    FILESYSTEMDB = 'filesystem'
```

**Usage**:
```python
from run_record_archiver.enums import DatabaseType

# Detect database type from URI
if database_uri.startswith('mongodb://'):
    db_type = DatabaseType.MONGODB
elif database_uri.startswith('filesystemdb://'):
    db_type = DatabaseType.FILESYSTEMDB
else:
    raise ConfigurationError(f"Unknown database type in URI: {database_uri}")

# Type-specific logic
if db_type == DatabaseType.MONGODB:
    # MongoDB-specific operations
    pass
elif db_type == DatabaseType.FILESYSTEMDB:
    # FilesystemDB-specific operations
    pass
```

---

#### SignalType

**Purpose**: Unix signal numbers for signal handling.

```python
class SignalType(IntEnum):
    SIGINT = 2
    SIGTERM = 15
```

**Usage**:
```python
from run_record_archiver.enums import SignalType
import signal

def signal_handler(signum, frame):
    if signum == SignalType.SIGINT:
        logger.info("Received SIGINT - graceful shutdown")
    elif signum == SignalType.SIGTERM:
        logger.info("Received SIGTERM - graceful shutdown")

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
```

---

#### FuzzMode

**Purpose**: Fuzzing/testing mode types for failure simulation.

```python
class FuzzMode(str, Enum):
    SKIP = 'skip'
    ERROR = 'error'
    NONE = 'none'
```

**Usage**:
```python
from run_record_archiver.enums import FuzzMode
import random

def determine_fuzz_action(config: AppFuzzConfig) -> FuzzMode:
    if random.random() < config.random_skip_percent / 100:
        return FuzzMode.SKIP
    elif random.random() < config.random_error_percent / 100:
        return FuzzMode.ERROR
    else:
        return FuzzMode.NONE

fuzz_mode = determine_fuzz_action(config.app_fuzz)

if fuzz_mode == FuzzMode.SKIP:
    logger.warning("Fuzzing: Skipping run (no error)")
    return True  # Fake success
elif fuzz_mode == FuzzMode.ERROR:
    raise FuzzSkipError("Fuzzing: Random error")
```

---

### Type Safety Benefits

#### 1. IDE Autocomplete

```python
# Type: Stage triggers autocomplete
stage = Stage.  # IDE suggests: IMPORT, MIGRATION, etc.
```

#### 2. Type Checking

```python
# mypy catches invalid values
stage: Stage = "invalid"  # Error: incompatible type
stage: Stage = Stage.IMPORT  # OK
```

#### 3. Exhaustive Checking

```python
# mypy can verify all enum cases are handled
def handle_stage(stage: Stage) -> None:
    if stage == Stage.IMPORT:
        pass
    elif stage == Stage.MIGRATION:
        pass
    # mypy warns if RECOVERY_IMPORT is not handled
```

#### 4. Documentation

```python
# Function signature documents valid values
def process_stage(stage: Stage) -> bool:
    """
    Process a pipeline stage.
    
    Args:
        stage: Pipeline stage (Import, Migration, etc.)
    """
```

---

## utils.py - Utility Functions

**Purpose**: Performance monitoring and metrics collection utilities.

**Location**: `~/run_record_archiver/dist/run_record_archiver/utils.py`

### Functions

#### performance_monitor

**Purpose**: Decorator for monitoring function execution time with optional Carbon metrics reporting.

**Signature**:
```python
def performance_monitor(func: Callable) -> Callable:
    """
    Decorator that logs execution time and reports to Carbon if enabled.
    
    Args:
        func: Function to monitor
        
    Returns:
        Wrapped function that logs execution time
    """
```

**Features**:
- Logs execution time at DEBUG level
- Reports metrics to Carbon/Graphite if enabled
- Uses `time.perf_counter()` for high-resolution timing
- Preserves function metadata with `@wraps`

**Usage Example**:
```python
from run_record_archiver.utils import performance_monitor

class Migrator:
    def __init__(self, config, carbon_client):
        self.carbon_client = carbon_client
    
    @performance_monitor
    def export_run(self, run_number: int) -> Path:
        """Export run from artdaqDB."""
        # ... export logic ...
        return export_path
    
    @performance_monitor
    def create_blob(self, run_number: int, export_dir: Path) -> bytes:
        """Create text blob from exported files."""
        # ... blob creation logic ...
        return blob_data
```

**Log Output**:
```
DEBUG - PERF: Migrator.export_run executed in 1234.56 ms.
DEBUG - PERF: Migrator.create_blob executed in 567.89 ms.
```

**Carbon Metrics**:
If Carbon client is enabled, metrics are posted with paths:
```
<metric_prefix>.Migrator.export_run.duration_ms: 1234.56
<metric_prefix>.Migrator.create_blob.duration_ms: 567.89
```

**Implementation Details**:
```python
@wraps(func)
def wrapper(*args, **kwargs) -> Any:
    logger = logging.getLogger(func.__module__)
    start_time = time.perf_counter()
    
    try:
        return func(*args, **kwargs)
    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.debug(
            'PERF: %s.%s executed in %.2f ms.',
            func.__module__, func.__name__, duration_ms
        )
        
        # Post to Carbon if enabled
        if args and hasattr(args[0], 'carbon_client'):
            carbon_client = args[0].carbon_client
            if carbon_client and carbon_client.enabled:
                metric_path = f'{args[0].__class__.__name__}.{func.__name__}.duration_ms'
                carbon_client.post_metric(metric_path, duration_ms)
```

**Requirements**:
- Function must be a method (first arg is `self`)
- `self` must have `carbon_client` attribute (can be None)
- Carbon client must have `enabled` property and `post_metric()` method

---

## base_stage.py - Abstract Base Class for Pipeline Stages

**Purpose**: Provides an abstract base class for pipeline stages using the Template Method pattern, eliminating code duplication and ensuring consistent behavior.

**Location**: `~/run_record_archiver/dist/run_record_archiver/base_stage.py`

### Design Pattern: Template Method

The `BaseStage` class implements the Template Method pattern:
- **Template methods** (`run`, `run_failure_recovery`) define the skeleton of the algorithm
- **Abstract methods** (must be implemented by subclasses) provide customization points
- **Concrete methods** (provided by base class) implement common behavior

This pattern ensures:
- Consistent retry logic across stages
- Uniform batch processing behavior
- Standardized state tracking
- Shared shutdown handling

---

### Class Definition

```python
class BaseStage(ABC):
    """
    Abstract base class for pipeline stages.
    
    Provides common functionality for:
    - Batch processing with concurrency
    - Retry logic with exponential backoff
    - State tracking and failure logging
    - Graceful shutdown handling
    """
    
    def __init__(self, config: Config):
        self._config = config
        self._logger = logging.getLogger(self.__class__.__name__)
        self._shutdown_check: Callable[[], bool] = lambda: False
```

---

### Abstract Methods (Must Implement)

Subclasses **must** implement these methods:

#### _get_work_items

```python
@abstractmethod
def _get_work_items(self, incremental: bool) -> List[int]:
    """
    Determine which runs to process.
    
    Args:
        incremental: If True, process only runs after last successful contiguous run
        
    Returns:
        List of run numbers to process
        
    Raises:
        ArchiverError: If unable to determine work items
    """
```

**Example Implementation (Importer)**:
```python
def _get_work_items(self, incremental: bool) -> List[int]:
    # Get candidate runs from filesystem
    filesystem_runs = self._get_candidate_runs()
    
    # Query artdaqDB for existing runs
    existing_runs = self.artdaq_client.query_runs()
    
    # Determine new runs to import
    new_runs = set(filesystem_runs) - set(existing_runs)
    
    if incremental:
        # Filter to runs after last contiguous
        state_data = state.read_state(self._get_state_file_path())
        last_contiguous = state_data.get('last_contiguous_run', 0)
        new_runs = [r for r in new_runs if r > last_contiguous]
    
    return sorted(new_runs)
```

---

#### _process_single_item

```python
@abstractmethod
def _process_single_item(self, run_number: int) -> bool:
    """
    Process a single run.
    
    Args:
        run_number: Run number to process
        
    Returns:
        True if successful, False otherwise
        
    Raises:
        ArchiverError: On processing errors (will be retried)
        FuzzSkipError: On permanent failures (will not be retried)
    """
```

**Example Implementation (Migrator)**:
```python
def _process_single_item(self, run_number: int) -> bool:
    # Export run from artdaqDB
    export_dir = self.artdaq_client.export_run(run_number)
    
    # Create text blob
    blob_data = self.blob_creator.create_blob(run_number, export_dir)
    
    # Upload to UconDB
    self.ucondb_client.upload_blob(run_number, blob_data)
    
    # Verify integrity
    self.ucondb_client.verify_upload(run_number, blob_data)
    
    return True
```

---

#### _get_state_file_path

```python
@abstractmethod
def _get_state_file_path(self) -> Path:
    """
    Get path to state file for this stage.
    
    Returns:
        Path to state file (e.g., importer_state.json, migrator_state.json)
    """
```

**Example Implementation**:
```python
def _get_state_file_path(self) -> Path:
    return self._config.app.import_state_file
```

---

#### _get_failure_log_path

```python
@abstractmethod
def _get_failure_log_path(self) -> Path:
    """
    Get path to failure log for this stage.
    
    Returns:
        Path to failure log (e.g., import_failures.log, migrate_failures.log)
    """
```

**Example Implementation**:
```python
def _get_failure_log_path(self) -> Path:
    return self._config.app.import_failure_log
```

---

#### _get_stage_name

```python
@abstractmethod
def _get_stage_name(self) -> str:
    """
    Get human-readable stage name for logging.
    
    Returns:
        Stage name (e.g., "Import", "Migration")
    """
```

**Example Implementation**:
```python
def _get_stage_name(self) -> str:
    return "Import"
```

---

### Concrete Methods (Provided by Base Class)

#### set_shutdown_check

```python
def set_shutdown_check(self, shutdown_check_func: Callable[[], bool]) -> None:
    """
    Set shutdown check function.
    
    Args:
        shutdown_check_func: Function that returns True if shutdown requested
    """
```

**Usage**:
```python
importer = Importer(config, clients)
importer.set_shutdown_check(lambda: signal_handler.shutdown_requested)
```

---

#### run

```python
def run(self, incremental: bool = False) -> int:
    """
    Execute the stage (template method).
    
    Args:
        incremental: Process only new runs since last successful contiguous run
        
    Returns:
        Exit code (0 for success, 1 for failure)
    """
```

**Algorithm**:
1. Call `_get_work_items(incremental)` to determine runs to process
2. If no work, return success
3. Call `_process_batch(runs)` to process runs concurrently
4. If successful runs exist, update state file with `update_contiguous_run_state()`
5. Return exit code

**Usage**:
```python
# Normal mode
exit_code = importer.run(incremental=False)

# Incremental mode
exit_code = importer.run(incremental=True)
```

---

#### run_failure_recovery

```python
def run_failure_recovery(self) -> int:
    """
    Retry failed runs from failure log (template method).
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
```

**Algorithm**:
1. Read failure log with `read_failure_log()`
2. If no failed runs, return success
3. Clear failure log (fresh start)
4. Call `_process_batch(failed_runs)` to retry
5. If successful runs exist, update state file
6. Return exit code

**Usage**:
```python
exit_code = importer.run_failure_recovery()
```

---

#### _get_max_workers

```python
def _get_max_workers(self) -> int:
    """
    Get number of worker threads.
    
    Returns:
        Number of workers from config.app.parallel_workers
    """
```

**Can be overridden** by subclasses if different parallelism is needed.

---

#### _process_run_with_retry

```python
def _process_run_with_retry(self, run_number: int) -> bool:
    """
    Process a single run with retry logic.
    
    Args:
        run_number: Run number to process
        
    Returns:
        True if successful (after any retries), False otherwise
    """
```

**Algorithm**:
1. Loop for `run_process_retries + 1` attempts
2. Log attempt number
3. Call `_process_single_item(run_number)`
4. If successful, return True
5. If `FuzzSkipError`, log permanent failure and return False (no retry)
6. If `ArchiverError`, log error and retry with delay
7. After all attempts exhausted, return False

**Retry Delay**: Uses `config.app.retry_delay_seconds` between attempts (no exponential backoff at this level).

---

#### _process_batch

```python
def _process_batch(self, runs_to_process: List[int]) -> List[int]:
    """
    Process a batch of runs concurrently.
    
    Args:
        runs_to_process: List of run numbers to process
        
    Returns:
        List of successfully processed run numbers
    """
```

**Algorithm**:
1. Create ThreadPoolExecutor with `_get_max_workers()` workers
2. Submit `_process_run_with_retry(run)` for each run
3. Wait for futures to complete with `as_completed()`
4. Collect successful and failed runs
5. Report progress every `PROGRESS_REPORT_INTERVAL` runs
6. Check `_shutdown_check()` after each completion
7. If shutdown requested, call `_handle_shutdown()`
8. Log failed runs to failure log
9. Send failure report if failures occurred
10. Return list of successful runs

**Concurrency**: Uses `ThreadPoolExecutor` for I/O-bound parallelism.

**Progress Reporting**: Logs progress every 10 runs (configurable via `PROGRESS_REPORT_INTERVAL`).

**Shutdown Handling**: Cancels pending futures, waits for in-progress futures.

---

#### _handle_shutdown

```python
def _handle_shutdown(
    self,
    executor: ThreadPoolExecutor,
    future_map: dict,
    successful: List[int],
    failed: List[int],
    total: int,
    completed_count: int
) -> None:
    """
    Handle graceful shutdown during batch processing.
    
    Cancels pending futures and waits for in-progress futures to complete.
    """
```

**Algorithm**:
1. Attempt to cancel all incomplete futures
2. Log number of cancelled vs in-progress runs
3. Wait for in-progress runs to complete
4. Collect results from in-progress runs
5. Add to successful/failed lists

**Graceful**: Does not forcefully terminate in-progress work.

---

### Example: Extending BaseStage

```python
from pathlib import Path
from typing import List
from run_record_archiver.base_stage import BaseStage
from run_record_archiver.config import Config
from run_record_archiver.persistence import state

class Importer(BaseStage):
    """Import stage: Filesystem → ArtdaqDB"""
    
    def __init__(self, config: Config, artdaq_client, fcl_preparer):
        super().__init__(config)
        self.artdaq_client = artdaq_client
        self.fcl_preparer = fcl_preparer
    
    def _get_work_items(self, incremental: bool) -> List[int]:
        """Determine runs to import."""
        # Get runs from filesystem
        filesystem_runs = self._scan_filesystem()
        
        # Get runs already in artdaqDB
        existing_runs = self.artdaq_client.query_runs()
        
        # Find new runs
        new_runs = set(filesystem_runs) - set(existing_runs)
        
        if incremental:
            # Filter to runs after last contiguous
            state_data = state.read_state(self._get_state_file_path())
            last_contiguous = state_data.get('last_contiguous_run', 0)
            new_runs = {r for r in new_runs if r > last_contiguous}
        
        return sorted(new_runs)
    
    def _process_single_item(self, run_number: int) -> bool:
        """Import a single run."""
        # Get run record directory
        run_dir = self._config.source_files.run_records_dir / str(run_number)
        
        # Prepare FHiCL files
        prepared_dir = self.fcl_preparer.prepare_run(run_number, run_dir)
        
        # Insert into artdaqDB
        self.artdaq_client.insert_run(run_number, prepared_dir)
        
        return True
    
    def _get_state_file_path(self) -> Path:
        return self._config.app.import_state_file
    
    def _get_failure_log_path(self) -> Path:
        return self._config.app.import_failure_log
    
    def _get_stage_name(self) -> str:
        return "Import"
    
    def _scan_filesystem(self) -> List[int]:
        """Scan filesystem for run records."""
        run_records_dir = self._config.source_files.run_records_dir
        return [
            int(d.name)
            for d in run_records_dir.iterdir()
            if d.is_dir() and d.name.isdigit()
        ]
```

**Usage**:
```python
# Create importer
config = Config.from_file('config.yaml')
artdaq_client = ArtdaqDBClient(config)
fcl_preparer = FclPreparer(config)
importer = Importer(config, artdaq_client, fcl_preparer)

# Set shutdown check
importer.set_shutdown_check(lambda: signal_handler.shutdown_requested)

# Run import
exit_code = importer.run(incremental=True)

# Or retry failures
exit_code = importer.run_failure_recovery()
```

---

## decorators.py - Retry Decorators

**Purpose**: Provides reusable retry decorators with exponential backoff for handling transient failures.

**Location**: `~/run_record_archiver/dist/run_record_archiver/decorators.py`

### Decorators

#### @retry

**Purpose**: General-purpose retry decorator with exponential backoff.

**Signature**:
```python
def retry(
    max_attempts: int = 3,
    delay_seconds: float = 1.0,
    backoff_multiplier: float = 1.0,
    exceptions: Tuple[Type[Exception], ...] = (ArchiverError,),
    log_attempts: bool = True
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Retry decorator with exponential backoff.
    
    Args:
        max_attempts: Maximum number of attempts (default: 3)
        delay_seconds: Initial delay between retries (default: 1.0)
        backoff_multiplier: Delay multiplier for exponential backoff (default: 1.0)
        exceptions: Tuple of exception types to catch and retry (default: (ArchiverError,))
        log_attempts: Whether to log retry attempts (default: True)
        
    Returns:
        Decorator function
        
    Raises:
        Last exception raised if all attempts fail
    """
```

**Features**:
- Configurable retry attempts
- Exponential backoff (delay × backoff_multiplier^attempt)
- Exception filtering (only retry specific exceptions)
- Automatic logging of retry attempts
- Re-raises last exception if all attempts fail

**Usage Example 1: Simple Retry**:
```python
from run_record_archiver.decorators import retry
from run_record_archiver.exceptions import UconDBError

@retry(max_attempts=3, delay_seconds=2.0)
def upload_to_ucondb(data: bytes) -> bool:
    """Upload data to UconDB with automatic retry."""
    response = requests.post(url, data=data)
    if response.status_code != 200:
        raise UconDBError(f"Upload failed: {response.status_code}")
    return True

# Will retry up to 3 times with 2-second delays
upload_to_ucondb(blob_data)
```

**Usage Example 2: Exponential Backoff**:
```python
@retry(
    max_attempts=5,
    delay_seconds=1.0,
    backoff_multiplier=2.0,  # 1s, 2s, 4s, 8s
    exceptions=(UconDBError, requests.RequestException)
)
def fetch_from_ucondb(run_number: int) -> dict:
    """Fetch run data with exponential backoff."""
    response = requests.get(f"{url}/{run_number}")
    response.raise_for_status()
    return response.json()
```

**Usage Example 3: Silent Retries**:
```python
@retry(max_attempts=3, delay_seconds=1.0, log_attempts=False)
def check_connection() -> bool:
    """Check database connection (silent retries)."""
    return db.ping()
```

**Backoff Timing**:
- Attempt 1: No delay
- Attempt 2: `delay_seconds`
- Attempt 3: `delay_seconds × backoff_multiplier`
- Attempt 4: `delay_seconds × backoff_multiplier²`
- Etc.

**Log Output**:
```
WARNING - Attempt 1/3 failed for upload_to_ucondb: Upload failed: 500
INFO - Retrying upload_to_ucondb in 2.0 seconds...
INFO - Retry attempt 2/3 for upload_to_ucondb
WARNING - Attempt 2/3 failed for upload_to_ucondb: Upload failed: 500
INFO - Retrying upload_to_ucondb in 2.0 seconds...
INFO - Retry attempt 3/3 for upload_to_ucondb
ERROR - All 3 attempts failed for upload_to_ucondb
```

---

#### @retry_on_failure

**Purpose**: Specialized retry decorator for functions that return success/failure booleans.

**Signature**:
```python
def retry_on_failure(
    max_retries: int = 2,
    delay_seconds: float = 5.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
) -> Callable[[Callable[..., bool]], Callable[..., bool]]:
    """
    Retry decorator for boolean return functions.
    
    Retries if:
    - Function returns False
    - Function raises exception in exceptions tuple
    
    Args:
        max_retries: Number of retry attempts (default: 2)
        delay_seconds: Delay between retries (default: 5.0)
        exceptions: Tuple of exception types to catch and retry (default: (Exception,))
        
    Returns:
        Decorator function
        
    Raises:
        Last exception raised if exception occurs on final attempt
    """
```

**Features**:
- Retries on both `False` return and exceptions
- Fixed delay (no exponential backoff)
- Always logs retry attempts
- Re-raises exception on final attempt

**Usage Example 1: Retry on False**:
```python
from run_record_archiver.decorators import retry_on_failure

@retry_on_failure(max_retries=3, delay_seconds=5.0)
def verify_upload(run_number: int) -> bool:
    """Verify upload succeeded (retry if not)."""
    actual_md5 = get_uploaded_md5(run_number)
    expected_md5 = calculate_local_md5(run_number)
    return actual_md5 == expected_md5

# Will retry up to 3 times if verification fails
if verify_upload(12345):
    logger.info("Upload verified")
else:
    logger.error("Upload verification failed after retries")
```

**Usage Example 2: Retry on Exception or False**:
```python
from run_record_archiver.exceptions import ArtdaqDBError

@retry_on_failure(
    max_retries=2,
    delay_seconds=10.0,
    exceptions=(ArtdaqDBError, ConnectionError)
)
def check_database_ready() -> bool:
    """Check if database is ready (retry on error or not ready)."""
    try:
        status = db.get_status()
        return status == "ready"
    except ConnectionError:
        # Will be caught and retried
        raise

# Retries if:
# 1. Returns False (status != "ready")
# 2. Raises ArtdaqDBError or ConnectionError
success = check_database_ready()
```

**Log Output (False return)**:
```
INFO - verify_upload returned False, retrying in 5 seconds (attempt 1/3)...
INFO - verify_upload returned False, retrying in 5 seconds (attempt 2/3)...
```

**Log Output (Exception)**:
```
WARNING - check_database_ready raised exception (attempt 1/3): Connection refused
INFO - Retrying in 10 seconds...
WARNING - check_database_ready raised exception (attempt 2/3): Connection refused
INFO - Retrying in 10 seconds...
```

---

### Decorator Comparison

| Feature | @retry | @retry_on_failure |
|---------|--------|-------------------|
| **Purpose** | General retry with exceptions | Boolean return + exceptions |
| **Retry Trigger** | Specific exceptions | False return OR exceptions |
| **Backoff** | Exponential (configurable) | Fixed delay |
| **Return Type** | Any type `T` | `bool` |
| **Final Behavior** | Re-raise exception | Re-raise exception OR return False |
| **Logging** | Optional (`log_attempts`) | Always enabled |
| **Use Cases** | API calls, I/O operations | Validation, status checks |

---

### Best Practices

#### DO: Use @retry for External API Calls

```python
@retry(
    max_attempts=5,
    delay_seconds=2.0,
    backoff_multiplier=2.0,
    exceptions=(requests.RequestException, UconDBError)
)
def upload_blob(run_number: int, data: bytes) -> None:
    """Upload with exponential backoff."""
    response = requests.post(url, data=data, timeout=30)
    if response.status_code != 200:
        raise UconDBError(f"Upload failed: {response.status_code}")
```

#### DO: Use @retry_on_failure for Validation

```python
@retry_on_failure(max_retries=3, delay_seconds=10.0)
def verify_data_consistency(run_number: int) -> bool:
    """Verify data consistency with retries."""
    local_hash = compute_local_hash(run_number)
    remote_hash = fetch_remote_hash(run_number)
    return local_hash == remote_hash
```

#### DON'T: Retry on Permanent Errors

```python
# BAD - Will retry on invalid configuration
@retry(max_attempts=3)
def load_config(path: str) -> Config:
    return Config.from_file(path)  # ConfigurationError is permanent

# GOOD - Only retry transient errors
@retry(
    max_attempts=3,
    exceptions=(IOError, OSError)  # Only retry I/O errors
)
def read_file(path: str) -> str:
    with open(path) as f:
        return f.read()
```

#### DON'T: Excessive Retry Attempts

```python
# BAD - 100 retries is excessive
@retry(max_attempts=100, delay_seconds=1.0)
def flaky_operation():
    pass

# GOOD - Reasonable retry limit
@retry(max_attempts=5, delay_seconds=2.0, backoff_multiplier=2.0)
def flaky_operation():
    pass
```

---

## log_handler.py - Custom Logging

**Purpose**: Provides a custom log handler that rotates log files based on both size and age.

**Location**: `~/run_record_archiver/dist/run_record_archiver/log_handler.py`

### Class: SizeAndTimeRotatingFileHandler

**Purpose**: Extends `RotatingFileHandler` to rotate logs based on either size or age (whichever occurs first).

**Inheritance**:
```python
class SizeAndTimeRotatingFileHandler(RotatingFileHandler):
    """
    Log handler that rotates based on size OR age.
    
    Combines size-based rotation (from RotatingFileHandler) with
    time-based rotation (custom logic).
    """
```

---

### Constructor

```python
def __init__(
    self,
    filename: str,
    mode: str = 'a',
    max_bytes: int = 0,
    backup_count: int = 0,
    encoding: Optional[str] = None,
    delay: bool = False,
    max_age_seconds: Optional[int] = None
):
    """
    Initialize handler with size and age limits.
    
    Args:
        filename: Log file path
        mode: File open mode (default: 'a' for append)
        max_bytes: Maximum file size before rotation (0 = no size limit)
        backup_count: Number of backup files to keep
        encoding: File encoding (default: None for platform default)
        delay: Delay file opening until first emit (default: False)
        max_age_seconds: Maximum file age before rotation (None = no age limit)
    """
```

**Attributes**:
```python
max_age_seconds: Optional[int]              # Maximum log file age
_log_file_created_time: Optional[float]     # File creation timestamp
```

---

### Methods

#### shouldRollover

```python
def shouldRollover(self, record: logging.LogRecord) -> bool:
    """
    Determine if rollover should occur.
    
    Rollover occurs if:
    1. File size exceeds max_bytes (parent class check), OR
    2. File age exceeds max_age_seconds (custom check)
    
    Args:
        record: Log record being emitted
        
    Returns:
        True if rollover should occur
    """
```

**Algorithm**:
1. Call parent class `shouldRollover()` (size check)
2. If size limit exceeded, return True
3. If `max_age_seconds` is set:
   - Get file creation time
   - Calculate file age
   - If age ≥ `max_age_seconds`, return True
4. Otherwise, return False

---

#### doRollover

```python
def doRollover(self) -> None:
    """
    Perform log file rotation.
    
    Calls parent class rotation logic, then updates creation time tracking.
    """
```

**Algorithm**:
1. Call parent class `doRollover()` (rename files, create new log)
2. Update `_log_file_created_time` with new file's creation time

---

#### emit

```python
def emit(self, record: logging.LogRecord) -> None:
    """
    Emit a log record.
    
    Initializes creation time tracking on first emit if needed.
    """
```

**Algorithm**:
1. If creation time not tracked and file exists, set `_log_file_created_time`
2. Call parent class `emit()` to write record

---

### Usage Example

```python
from run_record_archiver.log_handler import SizeAndTimeRotatingFileHandler
from run_record_archiver.constants import (
    LOG_FILE_MAX_BYTES,
    LOG_FILE_MAX_AGE_SECONDS,
    LOG_FILE_BACKUP_COUNT
)
import logging

# Create handler with size and age limits
handler = SizeAndTimeRotatingFileHandler(
    filename='/var/log/archiver/archiver.log',
    max_bytes=LOG_FILE_MAX_BYTES,              # 500 MB
    backup_count=LOG_FILE_BACKUP_COUNT,        # 5 backups
    max_age_seconds=LOG_FILE_MAX_AGE_SECONDS   # 14 days
)

# Configure formatter
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
handler.setFormatter(formatter)

# Add to logger
logger = logging.getLogger('run_record_archiver')
logger.addHandler(handler)
logger.setLevel(logging.INFO)
```

**Log File Rotation**:
```
# Active log
archiver.log

# Rotated logs (newest to oldest)
archiver.log.1
archiver.log.2
archiver.log.3
archiver.log.4
archiver.log.5  # Oldest, will be deleted on next rotation
```

---

### Rotation Scenarios

#### Scenario 1: Size-Based Rotation

```python
# Configuration
max_bytes = 500 * 1024 * 1024  # 500 MB
max_age_seconds = 14 * 24 * 60 * 60  # 14 days

# Day 1: Log file grows to 500 MB
# → Rotation occurs (size limit reached)

# Day 1 (after rotation): New log file started
# → archiver.log (0 MB, 0 days old)
# → archiver.log.1 (500 MB, rotated today)
```

#### Scenario 2: Age-Based Rotation

```python
# Configuration
max_bytes = 500 * 1024 * 1024  # 500 MB
max_age_seconds = 14 * 24 * 60 * 60  # 14 days

# Day 14: Log file only 100 MB (below size limit)
# → Rotation occurs (age limit reached)

# Day 14 (after rotation): New log file started
# → archiver.log (0 MB, 0 days old)
# → archiver.log.1 (100 MB, rotated today)
```

#### Scenario 3: Mixed Rotation

```python
# Multiple rotations over time
archiver.log          # Active (50 MB, 3 days old)
archiver.log.1        # 500 MB, rotated 1 week ago (size)
archiver.log.2        # 200 MB, rotated 2 weeks ago (age)
archiver.log.3        # 500 MB, rotated 3 weeks ago (size)
archiver.log.4        # 150 MB, rotated 4 weeks ago (age)
archiver.log.5        # 500 MB, rotated 5 weeks ago (size)
# Older logs deleted (backup_count = 5)
```

---

### Integration with __main__.py

The handler is configured in the application entry point:

```python
# From __main__.py
if config.app.log_file:
    log_dir = config.app.log_file.parent
    log_dir.mkdir(parents=True, exist_ok=True)
    
    file_handler = SizeAndTimeRotatingFileHandler(
        filename=str(config.app.log_file),
        max_bytes=LOG_FILE_MAX_BYTES,
        backup_count=LOG_FILE_BACKUP_COUNT,
        max_age_seconds=LOG_FILE_MAX_AGE_SECONDS
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)
    logger.addHandler(file_handler)
```

**Benefits**:
- Prevents unbounded log file growth (size limit)
- Ensures regular rotation for low-activity systems (age limit)
- Automatic cleanup of old logs (backup count)
- No external log rotation tools needed (logrotate, etc.)

---

## Summary

This document covered the core modules that form the foundation of the Run Record Archiver:

1. **config.py**: Robust configuration management with YAML parsing, environment variable expansion, and validation
2. **exceptions.py**: Comprehensive exception hierarchy with contextual metadata for error handling
3. **constants.py**: Centralized constants to eliminate magic numbers
4. **enums.py**: Type-safe enumerations for better code clarity and IDE support
5. **utils.py**: Performance monitoring utilities with optional metrics reporting
6. **base_stage.py**: Abstract base class implementing the Template Method pattern for pipeline stages
7. **decorators.py**: Retry decorators with exponential backoff for handling transient failures
8. **log_handler.py**: Custom log handler with size and age-based rotation

These modules provide:
- **Type safety** (enums, type hints)
- **Code reuse** (BaseStage, decorators)
- **Maintainability** (constants, configuration)
- **Observability** (logging, metrics)
- **Reliability** (retry logic, error handling)

For module-specific implementation details, refer to the source files in `~/run_record_archiver/dist/run_record_archiver/`.
