# Services Package Documentation

## Overview

The `services` package provides core business logic components used throughout the Run Record Archiver pipeline. These services handle FHiCL configuration preparation, blob creation and validation, external process execution, and failure notifications.

**Package Location**: `run_record_archiver/services/`

**Key Responsibilities**:
- Transform run record configurations into FHiCL format for archival
- Create and extract text blobs from exported configurations
- Validate blob contents against expected metadata parameters
- Execute external CLI tools (bulkloader, bulkdownloader) with environment management
- Send failure notifications via email and Slack

**Service Dependencies**:
```
FclPreparer
    ↓ (uses)
fhiclutils module (converters/generators)
    ↓ (produces)
BlobCreator → BlobValidator
    ↓
ProcessRunner (bulkloader/bulkdownloader)
    ↓
Reporting (email/Slack notifications)
```

---

## Table of Contents

1. [FclPreparer](#fclpreparer) - FHiCL configuration preparation
2. [BlobCreator](#blobcreator) - Text blob creation and extraction
3. [BlobValidator](#blobvalidator) - Blob content validation
4. [ProcessRunner](#processrunner) - External process execution
5. [Reporting](#reporting) - Failure notifications
6. [Common Patterns](#common-patterns)

---

## FclPreparer

**Purpose**: Transforms run record configuration files (`.txt` format) into FHiCL format (`.fcl`) for archival in artdaqDB. Handles both initial configuration conversion and stop-time updates.

**Module**: `fcl_preparer.py`

### Class Definition

```python
class FclPreparer:
    def __init__(
        self,
        fcl_conf_dir: Path,
        fhiclize_config: Optional[FhiclizeGenerateConfig] = None
    )
```

### Constructor Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `fcl_conf_dir` | `Path` | Yes | Directory containing `schema.fcl` template file |
| `fhiclize_config` | `FhiclizeGenerateConfig` | No | Configuration controlling which files to convert/generate. Defaults to empty config (no conversions). |

**Raises**: `FclPreperationError` if `fcl_conf_dir` is not a valid directory.

### Public Methods

#### `prepare_fcl_for_archive(run_dir: Path, tmpdir_path: Path) -> str`

Prepares run configuration for initial archival by converting `.txt` files to `.fcl` format and generating derived files.

**Parameters**:
- `run_dir` (Path): Source directory containing run record files (e.g., `/daq/run_records/12345`)
- `tmpdir_path` (Path): Temporary directory for processed files (will be populated)

**Returns**: `str` - Configuration name extracted from `metadata.txt` (or `"standard"` if not found)

**Process**:
1. Copies all files from `run_dir` to `tmpdir_path`
2. Sets appropriate permissions (directories: 755, files: 444)
3. Converts `.txt` files to `.fcl` using registered converters (if enabled in config)
4. Generates `RunHistory.fcl` from metadata (if enabled in config)
5. Copies `schema.fcl` from `fcl_conf_dir`

**Raises**: `FclPreperationError` on I/O errors or missing schema file

**Example**:
```python
from pathlib import Path
from run_record_archiver.services.fcl_preparer import FclPreparer
from run_record_archiver.config import FhiclizeGenerateConfig

# Create config to convert all known files
config = FhiclizeGenerateConfig({
    'converters': ['metadata', 'boot', 'settings', 'setup', 'environment', 'ranks'],
    'generators': ['RunHistory']
})

preparer = FclPreparer(
    fcl_conf_dir=Path("/path/to/fcl/conf"),
    fhiclize_config=config
)

# Prepare run 12345 for archival
run_dir = Path("/daq/run_records/12345")
tmp_dir = Path("/tmp/prepare_12345")
config_name = preparer.prepare_fcl_for_archive(run_dir, tmp_dir)
# Result: tmp_dir now contains *.fcl files ready for bulkloader
```

#### `prepare_fcl_for_update(run_dir: Path, tmpdir_path: Path) -> bool`

Prepares stop-time update data by extracting start/stop timestamps from metadata.

**Parameters**:
- `run_dir` (Path): Source directory containing `metadata.txt` with stop-time info
- `tmpdir_path` (Path): Temporary directory for generated `RunHistory2.fcl`

**Returns**: `bool` - `True` if update was prepared, `False` if skipped (no stop-time or disabled in config)

**Process**:
1. Checks if `RunHistory2` generation is enabled in config
2. Extracts "DAQInterface start time" and "DAQInterface stop time" from `metadata.txt`
3. Generates `RunHistory2.fcl` with extracted timestamps
4. Copies `schema.fcl` from `fcl_conf_dir`

**Raises**: `FclPreperationError` on I/O errors or missing schema file

**Example**:
```python
# Prepare stop-time update for run 12345
tmp_dir = Path("/tmp/update_12345")
has_update = preparer.prepare_fcl_for_update(run_dir, tmp_dir)

if has_update:
    # RunHistory2.fcl was generated with stop-time
    # Ready for second bulkloader call to update artdaqDB
    pass
```

### Configuration Requirements

**Required Files**:
- `fcl_conf_dir/schema.fcl` - FHiCL schema template (copied to output directory)

**FhiclizeGenerateConfig Structure**:
```yaml
fhiclize_generate:
  converters:
    - metadata          # metadata.txt → metadata.fcl
    - boot              # boot.txt → boot.fcl
    - known_boardreaders_list  # known_boardreaders_list.txt → *.fcl
    - settings          # settings.txt → settings.fcl
    - setup             # setup.txt → setup.fcl
    - environment       # environment.txt → environment.fcl
    - ranks             # ranks.txt → ranks.fcl
  generators:
    - RunHistory        # Generated from metadata.txt (initial archive)
    - RunHistory2       # Generated from metadata.txt (stop-time update)
```

### Converter Registry

Internal mapping of file basenames to converter functions:

```python
self._converter_map = {
    'metadata': fhiclize_metadata,
    'boot': fhiclize_boot,
    'known_boardreaders_list': fhiclize_known_boardreaders_list,
    'settings': fhiclize_settings,
    'setup': fhiclize_setup,
    'environment': fhiclize_environment,
    'ranks': fhiclize_ranks
}
```

All converters are implemented in the `fhiclutils` module.

### Error Handling

**Exceptions Raised**:
- `FclPreperationError`: Wraps `IOError`, `shutil.Error` during file operations
- `FclPreperationError`: If `fcl_conf_dir` is not a directory
- `FclPreperationError`: If `schema.fcl` not found

**Logging**:
- DEBUG: Conversion/generation success messages
- WARNING: Missing converters, missing metadata, no stop-time found

---

## BlobCreator

**Purpose**: Creates unified text blobs from exported configuration directories and extracts files from blobs. Used during migration stage to package artdaqDB exports for UconDB upload.

**Module**: `blob_creator.py`

### Class Definition

```python
class BlobCreator:
    def __init__(self) -> None
```

### Constructor Parameters

None. The class is stateless and requires no configuration.

### Public Methods

#### `create_blob_from_directory(run_number: int, source_dir: Path) -> str`

Creates a text blob by concatenating all files in a directory with structured headers/footers.

**Parameters**:
- `run_number` (int): Run number for header/footer metadata
- `source_dir` (Path): Directory containing exported configuration files

**Returns**: `str` - Complete text blob ready for upload

**Blob Structure**:
```
Start of Record
Run Number: 12345
Packed on Oct 26 14:30 UTC

#####
filename1.fcl:
#####
[file content]

#####
filename2.fcl:
#####
[file content]

...

End of Record
Run Number: 12345
Packed on Oct 26 14:30 UTC
```

**File Ordering**:
1. Regular files (alphabetically sorted)
2. Special files in fixed order:
   - `boot.fcl`
   - `known_boardreaders_list.fcl`
   - `setup.fcl`
   - `environment.fcl`
   - `metadata.fcl`
   - `settings.fcl`
   - `ranks.fcl`
   - `RunHistory.fcl`
   - `RunHistory2.fcl`

**Raises**: `BlobCreationError` if source directory is empty or file operations fail

**Example**:
```python
from run_record_archiver.services.blob_creator import BlobCreator

creator = BlobCreator()

# Create blob from exported run
blob_text = creator.create_blob_from_directory(
    run_number=12345,
    source_dir=Path("/tmp/exported/12345")
)

# Upload to UconDB
ucondb_client.upload_blob(run_number=12345, blob=blob_text)
```

#### `extract_files_from_blob(blob: str, output_dir: Path) -> Dict[str, Path]`

Extracts individual files from a blob and writes them to a directory.

**Parameters**:
- `blob` (str): Text blob containing multiple files
- `output_dir` (Path): Destination directory (will be created if it doesn't exist)

**Returns**: `Dict[str, Path]` - Mapping of filenames to their extracted paths

**Process**:
1. Creates `output_dir` if needed
2. Parses blob using regex pattern: `\n#####\n(.+?):\n#####\n`
3. Extracts content between markers
4. Writes each file to `output_dir/filename`
5. Preserves subdirectory structure from relative paths

**Raises**: `BlobCreationError` if no file markers found or file operations fail

**Example**:
```python
# Download blob from UconDB
blob = ucondb_client.download_blob(run_number=12345)

# Extract files for inspection
files = creator.extract_files_from_blob(
    blob=blob,
    output_dir=Path("/tmp/verify/12345")
)

# Result: files = {
#     'metadata.fcl': Path('/tmp/verify/12345/metadata.fcl'),
#     'settings.fcl': Path('/tmp/verify/12345/settings.fcl'),
#     ...
# }
```

### Configuration Requirements

None. The class is self-contained.

### Error Handling

**Exceptions Raised**:
- `BlobCreationError`: If source directory is empty
- `BlobCreationError`: If blob parsing fails (no markers found)
- `BlobCreationError`: Wraps general exceptions during blob operations

**Logging**:
- DEBUG: File extraction progress, individual file names
- WARNING: Non-UTF-8 files (falls back to ASCII decoding)
- INFO: Summary of extracted file count

---

## BlobValidator

**Purpose**: Validates blob contents by parsing FHiCL parameters and verifying expected metadata fields exist. Used during migration stage to ensure blob integrity before upload.

**Module**: `blob_validator.py`

### Class Definition

```python
class BlobValidator:
    def __init__(
        self,
        parameter_spec: Dict[str, Dict[str, str]] = None
    )
```

### Constructor Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `parameter_spec` | `Dict[str, Dict[str, str]]` | No | Mapping of files to expected parameters. Defaults to `DEFAULT_PARAMETER_SPEC`. |

**Default Parameter Spec**:
```python
DEFAULT_PARAMETER_SPEC = {
    'metadata.fcl': {
        'components': 'components',           # FHiCL key: components
        'configuration': 'config_name',       # FHiCL key: config_name
        'projectversion': 'myexpaq_commit_or_version'  # FHiCL key: myexpaq_commit_or_version
    }
}
```

Format: `{filename: {param_name: fhicl_key}}`

### Public Methods

#### `validate_blob(blob: str, run_number: int) -> Tuple[int, Dict[str, str]]`

Main validation method that checks blob structure and parameter extraction.

**Parameters**:
- `blob` (str): Text blob to validate
- `run_number` (int): Run number for logging purposes

**Returns**: `Tuple[int, Dict[str, str]]`
- `int`: Error count (0 = validation passed)
- `Dict[str, str]`: Extracted parameter values or error messages

**Validation Checks**:
1. Blob can be unpacked (file markers present)
2. Required files exist in blob
3. Each parameter has exactly one match (no duplicates)
4. Parameter values can be extracted

**Success Example**:
```python
validator = BlobValidator()
blob = "... blob content ..."

error_count, results = validator.validate_blob(blob, run_number=12345)
# error_count = 0
# results = {
#     'components': '8',
#     'configuration': 'standard_run_config',
#     'projectversion': 'v1_10_02'
# }
```

**Failure Example**:
```python
error_count, results = validator.validate_blob(bad_blob, run_number=12345)
# error_count = 2
# results = {
#     'components': "Error: file 'metadata.fcl' not found",
#     'configuration': "Error: multiple matches for parameter 'config_name'",
#     'projectversion': 'v1_10_02'
# }
```

#### `unpack_blob(blob: str) -> Dict[str, str]`

Low-level method to extract files from blob into memory.

**Parameters**:
- `blob` (str): Text blob

**Returns**: `Dict[str, str]` - Mapping of filenames to file contents

**Example**:
```python
files = validator.unpack_blob(blob)
# files = {
#     'metadata.fcl': 'components: "8"\nconfig_name: "standard"\n...',
#     'settings.fcl': '...',
#     ...
# }
```

#### `parse_metadata(metadata_content: str, file_spec: Dict[str, str]) -> Tuple[int, Dict[str, str]]`

Parses FHiCL content to extract specific parameters.

**Parameters**:
- `metadata_content` (str): FHiCL file content
- `file_spec` (Dict[str, str]): Parameter mapping `{param_name: fhicl_key}`

**Returns**: `Tuple[int, Dict[str, str]]`
- `int`: Error count
- `Dict[str, str]`: Extracted values or error messages

**FHiCL Parsing**:
Uses regex pattern: `{fhicl_key}:\s+(.+)`

**Example**:
```python
content = 'components: "8"\nconfig_name: "standard"\n'
spec = {'num_components': 'components', 'config': 'config_name'}

error_count, results = validator.parse_metadata(content, spec)
# error_count = 0
# results = {'num_components': '8', 'config': 'standard'}
```

### Configuration Requirements

**Custom Parameter Spec**:
```python
custom_spec = {
    'metadata.fcl': {
        'run_number': 'run_number',
        'config_name': 'config_name'
    },
    'settings.fcl': {
        'trigger_mode': 'trigger_mode'
    }
}

validator = BlobValidator(parameter_spec=custom_spec)
```

### Error Handling

**Exceptions Raised**:
- None directly. Catches all exceptions and returns them in results dict.

**Logging**:
- DEBUG: Extracted file count from blob
- INFO: Validation success with extracted values
- WARNING: Validation failures with error count
- ERROR: Blob unpacking failures

**Error Messages in Results**:
- `"Error: no matches for parameter '{key}'"`
- `"Error: multiple matches for parameter '{key}'"`
- `"Error: file '{filename}' not found"`
- `"Failed to unpack blob: {exception}"`

---

## ProcessRunner

**Purpose**: Executes external CLI tools (`bulkloader` and `bulkdownloader`) with proper environment setup, remote host support, and error handling.

**Module**: `process_runner.py`

### Functions

#### `run_bulkloader(run_number, config_name, data_dir, archive_uri, remote_host)`

Executes `bulkloader` CLI tool to import configuration into artdaqDB.

**Signature**:
```python
def run_bulkloader(
    run_number: int,
    config_name: str,
    data_dir: Path,
    archive_uri: str,
    remote_host: Optional[str]
) -> None
```

**Parameters**:
- `run_number` (int): Run number for bulkloader `-r` flag
- `config_name` (str): Configuration name for `-c` flag
- `data_dir` (Path): Directory containing `.fcl` files to import
- `archive_uri` (str): ArtdaqDB connection URI (e.g., `mongodb://host:port/database`)
- `remote_host` (Optional[str]): SSH hostname to run bulkloader remotely, or `None` for local

**Environment Setup**:
Automatically exports required environment variables:
- `PATH` - Adds `lib/` directory for bulkloader binary
- `LD_LIBRARY_PATH` - From current environment (for shared libraries)
- `PYTHONPATH` - From current environment (for conftoolp)
- `ARTDAQ_DATABASE_DATADIR` - From current environment
- `ARTDAQ_DATABASE_CONFDIR` - From current environment
- `ARTDAQ_DATABASE_URI` - Set to `archive_uri` parameter

**Local Execution**:
```bash
export PATH="<project>/lib:$PATH"
export LD_LIBRARY_PATH="..."
export ARTDAQ_DATABASE_URI="mongodb://..."
cd <data_dir>
bulkloader -r 12345 -c "config_name" -p <data_dir> -t $(( $(nproc)/2 ))
```

**Remote Execution (via SSH)**:
```bash
tar czf - -C <data_dir> . | \
ssh -o "StrictHostKeyChecking=no" ... <remote_host> \
  'mkdir -p /tmp/bulkloader_12345_<pid>; \
   cd /tmp/bulkloader_12345_<pid>; \
   tar xzf -; \
   export PATH=...; export LD_LIBRARY_PATH=...; export ARTDAQ_DATABASE_URI=...; \
   bulkloader -r 12345 -c "config_name" -p /tmp/bulkloader_12345_<pid> -t $(( $(nproc)/2 )); \
   cd /; \
   rm -rf /tmp/bulkloader_12345_<pid>'
```

**Raises**: `ArtdaqDBError` on subprocess failure or timeout (300s)

**Example**:
```python
from run_record_archiver.services.process_runner import run_bulkloader

run_bulkloader(
    run_number=12345,
    config_name="standard_config",
    data_dir=Path("/tmp/prepare_12345"),
    archive_uri="mongodb://localhost:27017/artdaqdb",
    remote_host=None  # Local execution
)
```

#### `run_bulkdownloader(run_number, config_name, destination_dir, archive_uri, remote_host)`

Executes `bulkdownloader` CLI tool to export configuration from artdaqDB.

**Signature**:
```python
def run_bulkdownloader(
    run_number: int,
    config_name: str,
    destination_dir: Path,
    archive_uri: str,
    remote_host: Optional[str]
) -> None
```

**Parameters**:
- `run_number` (int): Run number for bulkdownloader `-r` flag
- `config_name` (str): Configuration name for `-c` flag (just the name, not full path)
- `destination_dir` (Path): Directory to receive exported `.fcl` files (created if needed)
- `archive_uri` (str): ArtdaqDB connection URI
- `remote_host` (Optional[str]): SSH hostname to run bulkdownloader remotely, or `None`

**Local Execution**:
```bash
export PATH="<project>/lib:$PATH"
export LD_LIBRARY_PATH="..."
export ARTDAQ_DATABASE_URI="mongodb://..."
bulkdownloader -r 12345 -c "config_name" -p <destination_dir> -t $(( $(nproc)/2 ))
```

**Remote Execution (via SSH)**:
```bash
ssh -o "StrictHostKeyChecking=no" ... <remote_host> \
  'mkdir -p /tmp/bulkdownloader_12345_<pid>; \
   export PATH=...; export LD_LIBRARY_PATH=...; export ARTDAQ_DATABASE_URI=...; \
   bulkdownloader -r 12345 -c "config_name" -p /tmp/bulkdownloader_12345_<pid> -t $(( $(nproc)/2 )); \
   cd /tmp/bulkdownloader_12345_<pid>; \
   tar czf - .; \
   cd /; \
   rm -rf /tmp/bulkdownloader_12345_<pid>' | \
tar xzf - -C <destination_dir>
```

**Raises**: `ArtdaqDBError` on subprocess failure or timeout (300s)

**Example**:
```python
from run_record_archiver.services.process_runner import run_bulkdownloader

run_bulkdownloader(
    run_number=12345,
    config_name="standard_config",  # Just the name, not "12345/standard_config"
    destination_dir=Path("/tmp/exported/12345"),
    archive_uri="mongodb://localhost:27017/artdaqdb",
    remote_host="dbserver.example.com"  # Remote execution
)
```

### Configuration Requirements

**Environment Variables** (automatically propagated):
- `LD_LIBRARY_PATH` - Must include artdaq_database shared libraries
- `PYTHONPATH` - Must include conftoolp module path
- `ARTDAQ_DATABASE_DATADIR` - Data directory for artdaq_database
- `ARTDAQ_DATABASE_CONFDIR` - Config directory for artdaq_database

**SSH Requirements** (for remote execution):
- Passwordless SSH access to `remote_host`
- `bulkloader`/`bulkdownloader` available in remote PATH
- All shared libraries available on remote host

### Error Handling

**Exceptions Raised**:
- `ArtdaqDBError`: Wraps `subprocess.CalledProcessError` (non-zero exit code)
- `ArtdaqDBError`: Wraps `subprocess.TimeoutExpired` (300 second timeout)

**Error Messages Include**:
- Command that failed
- Exit code
- Full stdout output
- Full stderr output

**Logging**:
- DEBUG: Full command being executed, stdout output
- WARNING: Any stderr output (even on success)
- ERROR: Failure messages with complete error context

**Example Error**:
```python
try:
    run_bulkloader(...)
except ArtdaqDBError as e:
    # e.args[0] contains:
    # "Bulkloader failed with code 1.
    #  Cmd: bulkloader -r 12345 ...
    #  Stdout: ...
    #  Stderr: Error: Database connection failed"
    pass
```

---

## Reporting

**Purpose**: Sends failure notifications via email (SMTP) and/or Slack when runs fail during import or migration stages.

**Module**: `reporting.py`

### Functions

#### `send_failure_report(failed_runs, config, stage)`

Main entry point for sending failure notifications. Dispatches to email and/or Slack based on config.

**Signature**:
```python
def send_failure_report(
    failed_runs: List[int],
    config: ReportingConfig,
    stage: str
) -> None
```

**Parameters**:
- `failed_runs` (List[int]): Run numbers that failed (sorted in output)
- `config` (ReportingConfig): Reporting configuration (email and Slack settings)
- `stage` (str): Stage name for notification context (e.g., `"import"`, `"migrate"`)

**Behavior**:
1. Returns early if `failed_runs` is empty
2. Sends Slack notification if `config.slack.enabled` is `True`
3. Sends email if `config.email.enabled` is `True`
4. Operates on best-effort basis (logs errors but doesn't raise exceptions)

**Raises**: `ReportingError` only for email sending failures (Slack errors are logged but swallowed)

**Example**:
```python
from run_record_archiver.services.reporting import send_failure_report
from run_record_archiver.config import ReportingConfig

config = ReportingConfig({
    'email': {
        'enabled': True,
        'smtp_host': 'smtp.example.com',
        'smtp_port': 587,
        'sender_email': 'archiver@example.com',
        'recipient_email': 'ops@example.com'
    },
    'slack': {
        'enabled': True,
        'bot_token': 'xoxb-...',
        'channel': '#archiver-alerts'
    }
})

failed_runs = [12345, 12347, 12350]

send_failure_report(
    failed_runs=failed_runs,
    config=config,
    stage="import"
)
```

### Email Notifications

**Email Structure**:
```
Subject: Run Record Archiver Import Errors on hostname at 2025-10-24 14:30:45

Body:
The following runs failed during the import stage:

12345
12347
12350
```

**SMTP Configuration** (via `config.email`):
- `enabled` (bool): Enable/disable email notifications
- `smtp_host` (str): SMTP server hostname
- `smtp_port` (int): SMTP server port (typically 587 for TLS, 25 for plain)
- `smtp_use_tls` (bool): Whether to use STARTTLS
- `smtp_user` (Optional[str]): SMTP authentication username
- `smtp_password` (Optional[str]): SMTP authentication password
- `sender_email` (str): From address
- `recipient_email` (str): To address

**Example Config**:
```yaml
reporting:
  email:
    enabled: true
    smtp_host: smtp.gmail.com
    smtp_port: 587
    smtp_use_tls: true
    smtp_user: user@gmail.com
    smtp_password: app_password_here
    sender_email: archiver@example.com
    recipient_email: ops-team@example.com
```

### Slack Notifications

**Slack Message Structure**:

**Header Block**: `⚠️ Run Record Archiver Import Failures`

**Fields**:
- Host: `hostname`
- Time: `2025-10-24 14:30:45`
- Stage: `Import`
- Failed Runs: `3`

**Run Numbers**:
- If ≤10 runs: Full list (e.g., `12345, 12347, 12350`)
- If >10 runs: First 10 + count (e.g., `12345, 12347, ..., 12350, ... (25 more)`)

**Mentions**: Optional user mentions (e.g., `<@U123456> <@U789012>`)

**Slack Configuration** (via `config.slack`):
- `enabled` (bool): Enable/disable Slack notifications
- `bot_token` (str): Slack bot token (starts with `xoxb-`)
- `channel` (str): Channel to post to (e.g., `#archiver-alerts`)
- `mention_users` (Optional[str]): Comma-separated user IDs to mention (e.g., `U123456,U789012`)

**Example Config**:
```yaml
reporting:
  slack:
    enabled: true
    bot_token: xoxb-your-bot-token-here
    channel: "#archiver-alerts"
    mention_users: "U123456,U789012"  # Optional
```

**Slack Setup Requirements**:
1. Install `slack-bolt` library: `pip install slack-bolt`
2. Create Slack app with bot token scope: `chat:write`
3. Invite bot to target channel
4. Use bot token in configuration

See `~/run_record_archiver/run_record_archiver/slack.md` for detailed setup instructions.

### Configuration Requirements

**ReportingConfig Structure**:
```python
from run_record_archiver.config import ReportingConfig

config = ReportingConfig({
    'email': {
        'enabled': bool,
        'smtp_host': str,
        'smtp_port': int,
        'smtp_use_tls': bool,
        'smtp_user': Optional[str],
        'smtp_password': Optional[str],
        'sender_email': str,
        'recipient_email': str
    },
    'slack': {
        'enabled': bool,
        'bot_token': str,
        'channel': str,
        'mention_users': Optional[str]
    }
})
```

### Error Handling

**Email Errors**:
- Raises `ReportingError` on SMTP failures
- Logged at ERROR level with full exception details
- Common errors: `smtplib.SMTPException`, `socket.gaierror`, `TimeoutError`

**Slack Errors**:
- Logged at ERROR level but does NOT raise exceptions
- Operates on best-effort basis
- If `slack-bolt` library not installed: Logs warning and skips Slack notification

**Logging**:
- INFO: Successful notification sends (email/Slack)
- WARNING: `slack-bolt` library not available
- ERROR: SMTP connection failures, Slack API errors

---

## Common Patterns

### Service Integration in Pipeline Stages

**Import Stage** (Importer):
```python
from run_record_archiver.services.fcl_preparer import FclPreparer
from run_record_archiver.services.process_runner import run_bulkloader
from run_record_archiver.services.reporting import send_failure_report

class Importer:
    def __init__(self, config, artdaq_client, reporting_config):
        self.fcl_preparer = FclPreparer(
            fcl_conf_dir=config.fcl_conf_dir,
            fhiclize_config=config.fhiclize_generate
        )
        self.artdaq_client = artdaq_client
        self.reporting_config = reporting_config
        self.failed_runs = []
    
    def _process_run(self, run_number: int) -> bool:
        run_dir = self.source_dir / str(run_number)
        
        # Step 1: Prepare FHiCL files for initial import
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            config_name = self.fcl_preparer.prepare_fcl_for_archive(
                run_dir, tmp_path
            )
            
            # Step 2: Import to artdaqDB
            if self.use_tools:
                run_bulkloader(
                    run_number, config_name, tmp_path,
                    self.artdaq_uri, self.remote_host
                )
            else:
                self.artdaq_client.insert_config(
                    run_number, config_name, tmp_path
                )
        
        # Step 3: Prepare stop-time update
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            has_update = self.fcl_preparer.prepare_fcl_for_update(
                run_dir, tmp_path
            )
            
            if has_update:
                if self.use_tools:
                    run_bulkloader(
                        run_number, config_name, tmp_path,
                        self.artdaq_uri, self.remote_host
                    )
                else:
                    self.artdaq_client.update_config(
                        run_number, config_name, tmp_path
                    )
        
        return True
    
    def run(self):
        # Process runs...
        if self.failed_runs:
            send_failure_report(
                self.failed_runs,
                self.reporting_config,
                stage="import"
            )
```

**Migration Stage** (Migrator):
```python
from run_record_archiver.services.blob_creator import BlobCreator
from run_record_archiver.services.blob_validator import BlobValidator
from run_record_archiver.services.process_runner import run_bulkdownloader
from run_record_archiver.services.reporting import send_failure_report

class Migrator:
    def __init__(self, config, artdaq_client, ucondb_client, reporting_config):
        self.blob_creator = BlobCreator()
        self.blob_validator = BlobValidator()
        self.artdaq_client = artdaq_client
        self.ucondb_client = ucondb_client
        self.reporting_config = reporting_config
        self.failed_runs = []
    
    def _process_run(self, run_number: int) -> bool:
        # Step 1: Export from artdaqDB
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)
            config_name = self.artdaq_client.get_config_name(run_number)
            
            if self.use_tools:
                run_bulkdownloader(
                    run_number, config_name, export_dir,
                    self.artdaq_uri, self.remote_host
                )
            else:
                self.artdaq_client.export_config(
                    run_number, config_name, export_dir
                )
            
            # Step 2: Create blob
            blob = self.blob_creator.create_blob_from_directory(
                run_number, export_dir
            )
        
        # Step 3: Validate blob
        error_count, results = self.blob_validator.validate_blob(
            blob, run_number
        )
        
        if error_count > 0:
            self.logger.error(
                "Blob validation failed for run %d: %s",
                run_number, results
            )
            return False
        
        # Step 4: Upload to UconDB
        self.ucondb_client.upload_blob(run_number, blob)
        
        return True
    
    def run(self):
        # Process runs...
        if self.failed_runs:
            send_failure_report(
                self.failed_runs,
                self.reporting_config,
                stage="migrate"
            )
```

### Error Handling Best Practices

**Consistent Exception Wrapping**:
```python
from run_record_archiver.exceptions import (
    FclPreperationError,
    BlobCreationError,
    ArtdaqDBError,
    ReportingError
)

try:
    fcl_preparer.prepare_fcl_for_archive(run_dir, tmp_dir)
except FclPreperationError as e:
    logger.error("FCL preparation failed for run %d: %s", run_number, e)
    failed_runs.append(run_number)
    return False

try:
    blob = blob_creator.create_blob_from_directory(run_number, export_dir)
except BlobCreationError as e:
    logger.error("Blob creation failed for run %d: %s", run_number, e)
    failed_runs.append(run_number)
    return False
```

**Service-Specific Logging**:
```python
import logging

class MyService:
    def __init__(self):
        # Use __name__ for automatic module-based logger naming
        self._logger = logging.getLogger(__name__)
    
    def process(self):
        self._logger.debug("Starting processing")
        self._logger.info("Processing complete")
        self._logger.warning("Unusual condition detected")
        self._logger.error("Processing failed: %s", error)
```

### Temporary Directory Management

**Cleanup Pattern** (automatically removes temp files):
```python
import tempfile
from pathlib import Path

def process_run(run_number: int):
    # Context manager ensures cleanup even on exceptions
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Prepare files
        config_name = fcl_preparer.prepare_fcl_for_archive(
            run_dir, tmp_path
        )
        
        # Use files
        run_bulkloader(run_number, config_name, tmp_path, ...)
        
    # tmp_path automatically removed here
```

### Service Configuration Pattern

**Dependency Injection**:
```python
from run_record_archiver.config import Config
from run_record_archiver.services.fcl_preparer import FclPreparer
from run_record_archiver.services.blob_creator import BlobCreator

def create_services(config: Config):
    """Factory function for service instances"""
    return {
        'fcl_preparer': FclPreparer(
            fcl_conf_dir=config.fcl_conf_dir,
            fhiclize_config=config.fhiclize_generate
        ),
        'blob_creator': BlobCreator(),
        'blob_validator': BlobValidator(
            parameter_spec=config.blob_validation_spec
        )
    }

# Usage in Orchestrator
class Orchestrator:
    def __init__(self, config: Config):
        services = create_services(config)
        self.fcl_preparer = services['fcl_preparer']
        self.blob_creator = services['blob_creator']
        self.blob_validator = services['blob_validator']
```

### Remote vs Local Execution

**Conditional Logic Based on Config**:
```python
def import_config(run_number, config_name, data_dir):
    if config.artdaq_db.remote_host:
        # Remote execution via SSH
        run_bulkloader(
            run_number, config_name, data_dir,
            config.artdaq_db.uri,
            remote_host=config.artdaq_db.remote_host
        )
    else:
        # Local execution
        run_bulkloader(
            run_number, config_name, data_dir,
            config.artdaq_db.uri,
            remote_host=None
        )
```

---

## Related Documentation

- **Configuration Guide**: `~/run_record_archiver/run_record_archiver/config.md`
- **Importer Documentation**: `~/run_record_archiver/run_record_archiver/importer.md`
- **Migrator Documentation**: `~/run_record_archiver/run_record_archiver/migrator.md`
- **Slack Setup Guide**: `~/run_record_archiver/run_record_archiver/slack.md`
- **FHiCL Utilities**: See `run_record_archiver/fhiclutils.py` for converter implementations

---

## Service Dependency Graph

```
Configuration (config.yaml)
    ↓
FhiclizeGenerateConfig → FclPreparer
    ↓                        ↓
fhiclutils             prepare_fcl_for_archive()
    ↓                        ↓
.txt → .fcl          run_bulkloader() → ArtdaqDB
    ↓
run_bulkdownloader() → Exported Files
    ↓
BlobCreator.create_blob_from_directory()
    ↓
BlobValidator.validate_blob()
    ↓
UconDBClient.upload_blob()
    ↓
ReportingService.send_failure_report()
    ├── Email (SMTP)
    └── Slack (API)
```

---

## Testing Services

**Unit Test Examples**:
```python
import pytest
from pathlib import Path
from run_record_archiver.services.blob_creator import BlobCreator
from run_record_archiver.exceptions import BlobCreationError

def test_blob_creation_empty_directory():
    creator = BlobCreator()
    empty_dir = Path("/tmp/empty")
    empty_dir.mkdir(exist_ok=True)
    
    with pytest.raises(BlobCreationError, match="No config files found"):
        creator.create_blob_from_directory(12345, empty_dir)

def test_blob_extraction(tmp_path):
    creator = BlobCreator()
    blob = """Start of Record
Run Number: 12345

#####
test.fcl:
#####
content here

End of Record
"""
    files = creator.extract_files_from_blob(blob, tmp_path)
    assert 'test.fcl' in files
    assert (tmp_path / 'test.fcl').read_text() == 'content here'
```

See `tests/` directory for complete test suite.

---

**Document Version**: 1.0  
**Last Updated**: 2025-10-24  
**Maintained by**: Run Record Archiver Development Team
