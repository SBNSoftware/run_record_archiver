# File Formats Reference

This document provides comprehensive specifications for all file formats used by the Run Record Archiver.

## Table of Contents

1. [Configuration Files](#configuration-files)
2. [State Files](#state-files)
3. [Log Files](#log-files)
4. [FHiCL Files](#fhicl-files)
5. [Blob Files](#blob-files)
6. [Lock Files](#lock-files)

---

## Configuration Files

### config.yaml - Main Configuration

**Format:** YAML with variable expansion support

**Location:** User-specified (typically project root or `/etc/run_record_archiver/`)

**Structure:**

```yaml
# ============================================================================
# Application Settings
# ============================================================================
app:
    # Working directory paths
    work_dir: string                      # Base directory for all archiver files
    import_state_file: string             # Import stage state tracking (JSON)
    import_failure_log: string            # Failed import runs (text)
    migrate_state_file: string            # Migration stage state tracking (JSON)
    migrate_failure_log: string           # Failed migration runs (text)
    lock_file: string                     # Concurrent execution prevention

    # Processing parameters
    batch_size: integer                   # Maximum runs per execution (default: 50)
    parallel_workers: integer             # Number of concurrent threads (default: 4)
    run_process_retries: integer          # Retry attempts for failed runs (default: 2)
    retry_delay_seconds: integer          # Delay between retries in seconds (default: 5)

    # Logging configuration
    log_level: string                     # DEBUG|INFO|WARNING|ERROR|CRITICAL
    log_file: string|null                 # Log file path (null for stdout only)

# FHiCL file processing configuration
fhiclize_generate:
    - string                              # List of converters/generators to enable
    # Known converters (txt → fcl):
    #   - metadata, boot, settings, setup, environment
    #   - known_boardreaders_list, ranks
    # Known generators (generate from data):
    #   - RunHistory, RunHistory2

# Fuzzing/testing configuration (optional)
app_fuzz:
    random_skip_percent: integer          # % of runs to skip (0-100, testing only)
    random_skip_retry: boolean            # If true, skipped runs won't retry
    random_error_percent: integer         # % of runs to error (0-100, testing only)
    random_error_retry: boolean           # If true, errored runs won't retry

# ============================================================================
# Source Filesystem Settings (Import Stage)
# ============================================================================
source_files:
    run_records_dir: string               # Directory containing run record subdirectories
                                          # Format: /path/to/run_records/<run_number>/

# ============================================================================
# Intermediate Database Settings (ArtdaqDB)
# ============================================================================
artdaq_db:
    fcl_conf_dir: string                  # Directory containing schema.fcl
    database_uri: string                  # Database connection URI
                                          # FilesystemDB: filesystemdb:///absolute/path/to/db_archive
                                          # MongoDB: mongodb://user:pass@host:port/database_archive
    
    # Performance options
    use_tools: boolean                    # Use CLI tools vs Python API (default: false)
    remote_host: string|null              # Remote host for CLI tools (requires SSH)

# ============================================================================
# Destination Database Settings (UconDB)
# ============================================================================
ucon_db:
    server_url: string                    # UconDB server URL (must end with /app)
                                          # Format: https://hostname:port/instance/app
    folder_name: string                   # Folder within UconDB to store runs
    object_name: string                   # Object type identifier (typically "configuration")
    timeout_seconds: integer              # API request timeout (default: 10)
    writer_user: string                   # Authentication username
    writer_password: string               # Authentication password

# ============================================================================
# Notification Settings
# ============================================================================
reporting:
    # Email notification configuration
    email:
        enabled: boolean                  # Enable email alerts
        recipient_email: string           # Recipient addresses (comma-separated)
        sender_email: string              # From address
        smtp_host: string                 # SMTP server hostname
        smtp_port: integer                # SMTP server port (25, 587, 465)
        smtp_use_tls: boolean             # Enable STARTTLS encryption
        smtp_user: string|null            # Username for SMTP auth (optional)
        smtp_password: string|null        # Password for SMTP auth (optional)
    
    # Slack notification configuration
    slack:
        enabled: boolean                  # Enable Slack alerts
        bot_token: string                 # Slack Bot User OAuth Token (xoxb-...)
        channel: string                   # Channel name or ID (#channel or C123...)
        mention_users: string|null        # Comma-separated Slack user IDs for mentions

# ============================================================================
# Performance Metrics (Optional)
# ============================================================================
carbon:
    enabled: boolean                      # Enable metrics reporting
    host: string                          # Carbon server hostname/IP
    port: integer                         # Carbon line receiver port (default: 2003)
    metric_prefix: string                 # Metric namespace prefix
                                          # Example: experiment.run_archiver.environment
```

**Variable Expansion:**

The configuration supports two types of variable expansion:

1. **Environment Variables:** `${VAR}` or `${VAR:-default}`
   ```yaml
   work_dir: "${WORK_DIR:-/tmp/run_record_archiver}"
   ```

2. **Parameter References:** `${param}` (same section) or `${section.param}` (cross-section)
   ```yaml
   app:
       work_dir: "/tmp/archiver"
       import_state_file: "${work_dir}/importer_state.json"
   ```

**Validation:**
- Required sections: `app`, `source_files`, `artdaq_db`, `ucon_db`
- Optional sections: `reporting`, `carbon`, `app_fuzz`, `fhiclize_generate`
- All paths are validated for existence/accessibility at runtime

---

### tests_config.yaml - Test Configuration

**Format:** YAML

**Location:** Project root

**Structure:**

```yaml
# Test module execution modes
tests:
    test_module_name: true|mock|false
    # true: Run with real dependencies (requires full environment)
    # mock: Run with mocked dependencies (uses tests/mocks/)
    # false: Skip test entirely

tests_tools:
    test_tool_name: true|mock|false
    # Same mode system for comparison tool tests

# Test data paths
test_data:
    exported_run_dir: string              # Path to exported run records
    blob_output_dir: string               # Path for blob output
    test_run_number: integer              # Run number for testing

# Application configuration for integration tests
# (Full app config sections available here)
```

---

### archiver.env - Environment Variables

**Format:** Shell environment variable definitions

**Location:** Project root (automatically loaded by run_archiver.sh and run_tests.sh)

**Structure:**

```bash
# Experiment identification
EXPERIMENT_NAME=myexp

# Working directories
WORK_DIR=/tmp/run_record_archiver
RUN_RECORDS_DIR=/daq/run_records

# Database connections
ARTDAQDB_URL=filesystemdb:///path/to/artdaq_db_archive
UCONDB_URL=https://server.example.com:9443/myexp_on_ucon_prod/app

# Authentication
UCONDB_USER=archiver_user
UCONDB_PASSWORD=secure_password

# Notifications
NOTIFY_EMAIL_LIST=user1@example.com,user2@example.com
```

---

## State Files

### State JSON Files

**Files:**
- `importer_state.json` - Import stage state tracking
- `migrator_state.json` - Migration stage state tracking

**Format:** JSON

**Purpose:** Track incremental progress and enable resume capability

**Schema:**

```json
{
    "last_contiguous_run": integer,
    "last_attempted_run": integer
}
```

**Fields:**

- `last_contiguous_run` (integer): Last run number in an unbroken sequence of successful runs
  - Used to prevent gaps in archival
  - Example: If runs 100-105 succeed, 106 fails, 107 succeeds → value is 105
  - Next incremental run starts after this number

- `last_attempted_run` (integer): Highest run number that has been processed (success or failure)
  - Tracks all attempted runs, not just successful ones
  - Used by incremental mode to skip already-processed runs
  - Example: If runs 100-110 attempted (some failed) → value is 110
  - Next incremental run starts after MAX(last_contiguous_run, last_attempted_run)

**State Calculation Logic:**

```python
# Contiguous run tracking (prevents gaps)
current_last = state.get("last_contiguous_run", 0)
for run in sorted(successful_runs):
    if run == current_last + 1:
        current_last = run
    elif run > current_last + 1:
        break  # Gap detected, stop here

# Attempted run tracking (prevents re-processing)
last_attempted = state.get("last_attempted_run", 0)
new_last_attempted = max(max(attempted_runs), last_attempted)

# Incremental mode resume point
start_run = max(last_contiguous_run, last_attempted_run)
# Process runs > start_run
```

**Example Scenarios:**

1. **All successful (no gaps):**
   ```json
   {"last_contiguous_run": 105, "last_attempted_run": 105}
   ```
   Next run: 106

2. **With failures (gap created):**
   ```json
   {"last_contiguous_run": 102, "last_attempted_run": 107}
   ```
   Runs 103-104 failed, 105-107 succeeded
   Next run: 108 (failed runs 103-104 in failure log)

3. **Fresh start:**
   ```json
   {"last_contiguous_run": 0, "last_attempted_run": 0}
   ```
   Next run: 1

**File Operations:**
- Created automatically on first successful run
- Updated after each batch completion
- Read at startup for incremental mode
- Can be manually edited (use with caution)

---

### Failure Log Files

**Files:**
- `import_failures.log` - Failed import runs
- `migrate_failures.log` - Failed migration runs

**Format:** Plain text, one run number per line

**Purpose:** Track failed runs for targeted retry

**Structure:**

```
12345
12348
12350
```

**Characteristics:**
- One run number per line
- Sorted numerically (ascending)
- No comments or metadata
- Empty file = no failures
- Entries removed upon successful retry

**Operations:**

1. **Append Failed Run:**
   ```python
   with failure_log.open("a") as f:
       f.write(f"{run_number}\n")
   ```

2. **Read Failed Runs:**
   ```python
   failed_runs = [int(line.strip()) for line in f if line.strip().isdigit()]
   ```

3. **Update After Retry:**
   ```python
   # Remove successfully retried runs
   remaining_failures = [r for r in failed_runs if r not in successful_retries]
   with failure_log.open("w") as f:
       for run in sorted(remaining_failures):
           f.write(f"{run}\n")
   ```

**Usage with CLI:**
```bash
# Retry failed imports
./run_archiver.sh config.yaml --retry-failed-import

# Retry failed migrations
./run_archiver.sh config.yaml --retry-failed-migrate
```

---

## Log Files

### Application Log

**File:** Specified by `app.log_file` in config (e.g., `archiver.log`)

**Format:** Plain text with structured log lines

**Rotation Policy:**
- **Size-based:** Rotates when file exceeds 500 MB
- **Age-based:** Rotates when file is older than 2 weeks (14 days)
- **Backup count:** Maintains 5 backup files

**Rotation Constants:**
```python
LOG_FILE_MAX_BYTES = 500 * 1024 * 1024      # 500 MB
LOG_FILE_MAX_AGE_SECONDS = 14 * 24 * 60 * 60  # 2 weeks
LOG_FILE_BACKUP_COUNT = 5
```

**File Naming:**
```
archiver.log         # Current log
archiver.log.1       # Most recent backup
archiver.log.2       # Second most recent
archiver.log.3
archiver.log.4
archiver.log.5       # Oldest backup (will be deleted on next rotation)
```

**Log Line Format:**
```
YYYY-MM-DD HH:MM:SS,mmm - LEVEL - module_name - message
```

**Example:**
```
2025-10-24 14:32:15,123 - INFO - run_record_archiver.importer - Processing run 12345
2025-10-24 14:32:16,456 - DEBUG - run_record_archiver.clients.artdaq - Inserting to artdaqDB
2025-10-24 14:32:17,789 - ERROR - run_record_archiver.migrator - Failed to export run 12346: Connection timeout
```

**Log Levels:**
- `DEBUG`: Detailed diagnostic information (verbose mode only)
- `INFO`: General informational messages (default)
- `WARNING`: Warning messages (potential issues)
- `ERROR`: Error messages (operation failures)
- `CRITICAL`: Critical errors (system failures)

**Rotation Behavior:**
- Checked on every log emission
- Triggers on first condition met (size OR age)
- Old backups automatically deleted when exceeding backup count
- File creation time tracked for age-based rotation

**Implementation:**
```python
from run_record_archiver.log_handler import SizeAndTimeRotatingFileHandler

handler = SizeAndTimeRotatingFileHandler(
    filename="archiver.log",
    max_bytes=LOG_FILE_MAX_BYTES,
    max_age_seconds=LOG_FILE_MAX_AGE_SECONDS,
    backup_count=LOG_FILE_BACKUP_COUNT
)
```

---

## FHiCL Files

FHiCL (Fermilab Hierarchical Configuration Language) is a configuration format used by artdaq_database.

### Source File Types

The archiver processes various text files from run records and converts/generates FHiCL files:

#### 1. Converted Files (txt → fcl)

**metadata.txt → metadata.fcl**
```
# Source format (key-value pairs)
Config name: example_config
Run number: 12345
Start time: 2025-10-24T14:30:00
Component #0: tpc01
Component #1: tpc02

# FHiCL output
config_name: "example_config"
run_number: 12345
start_time: "2025-10-24T14:30:00"
components: ["tpc01", "tpc02"]
```

**boot.txt → boot.fcl**
```
# Source format (key-value pairs)
boot_mode: standard
partition: production

# FHiCL output
boot_mode: "standard"
partition: "production"
```

**settings.txt → settings.fcl**
```
# Source format (key-value pairs)
trigger_rate: 100
readout_window: 5000

# FHiCL output
trigger_rate: 100
readout_window: 5000
```

**setup.txt → setup.fcl**
```
# Source format (key-value pairs)
software_version: v1_2_3
configuration_id: config_abc123

# FHiCL output
software_version: "v1_2_3"
configuration_id: "config_abc123"
```

**environment.txt → environment.fcl**
```
# Source format (shell export statements)
export PATH=/usr/local/bin:/usr/bin
export ARTDAQ_VERSION=v3_12_00

# FHiCL output
environment: {
    PATH: "/usr/local/bin:/usr/bin"
    ARTDAQ_VERSION: "v3_12_00"
}
```

**ranks.txt → ranks.fcl**
```
# Source format (verbatim text)
tpc01: 0
tpc02: 1
crt01: 2

# FHiCL output
ranks: "tpc01: 0\ntpc02: 1\ncrt01: 2\n"
```

**known_boardreaders_list.txt → known_boardreaders_list.fcl**
```
# Source format (whitespace-separated tabular data)
tpc01 localhost -1
tpc02 myexp-tpc02 -1
crt01 host -1 1 0-15 "/usr/bin/cmd arg1 arg2"

# FHiCL output
tpc01: ["localhost", "-1"]
tpc02: ["myexp-tpc02", "-1"]
crt01: ["host", "-1", "1", "0-15", "/usr/bin/cmd arg1 arg2 "]
```

#### 2. Generated Files

**RunHistory.fcl** (generated from metadata.txt)
```fcl
run_number: 12345

config_name: "example_config"

components: ["tpc01", "tpc02", "crt01"]
```

**RunHistory2.fcl** (generated from metadata.txt stop-time)
```fcl
run_number: 12345

stop_time: "2025-10-24T15:45:00"
```

#### 3. Required Schema File

**schema.fcl** (copied from artdaq_database conf directory)

Defines the database schema for storing run configurations. This file is always required and copied from the artdaq_database installation.

### FHiCL Format Rules

1. **Key-Value Pairs:**
   ```fcl
   key: value
   string_key: "quoted value"
   numeric_key: 12345
   ```

2. **Arrays:**
   ```fcl
   array: ["value1", "value2", "value3"]
   ```

3. **Nested Objects:**
   ```fcl
   section: {
       nested_key: "value"
       nested_array: [1, 2, 3]
   }
   ```

4. **Comments:**
   ```fcl
   # This is a comment
   key: value  # Inline comment
   ```

5. **Value Quoting:**
   - Strings with spaces: Must be quoted
   - Numeric values: Unquoted
   - Special characters: Quoted
   - Already-quoted strings: Preserved as-is

### FHiCL Configuration

The `fhiclize_generate` section in config.yaml controls which files are processed:

```yaml
fhiclize_generate:
    - metadata           # Convert metadata.txt → metadata.fcl
    - boot              # Convert boot.txt → boot.fcl
    - settings          # Convert settings.txt → settings.fcl
    - setup             # Convert setup.txt → setup.fcl
    - environment       # Convert environment.txt → environment.fcl
    - ranks             # Convert ranks.txt → ranks.fcl
    - known_boardreaders_list  # Convert known_boardreaders_list.txt → .fcl
    - RunHistory        # Generate RunHistory.fcl from metadata
    - RunHistory2       # Generate RunHistory2.fcl from stop-time
```

**Partial Configuration Example:**
```yaml
# Only process metadata and boot files
fhiclize_generate:
    - metadata
    - boot
```

---

## Blob Files

Blob files are text concatenations of all FHiCL files for a run, used for UconDB storage.

**Format:** Plain text with structured delimiters

**Purpose:** Package multiple FHiCL files into a single uploadable text blob

### Blob Structure

```
Start of Record
Run Number: 12345
Packed on Oct 26 14:30 UTC

#####
ComponentConfig.fcl:
#####
<content of ComponentConfig.fcl>

#####
metadata.fcl:
#####
<content of metadata.fcl>

#####
boot.fcl:
#####
<content of boot.fcl>

#####
known_boardreaders_list.fcl:
#####
<content of known_boardreaders_list.fcl>

#####
setup.fcl:
#####
<content of setup.fcl>

#####
environment.fcl:
#####
<content of environment.fcl>

#####
metadata.fcl:
#####
<content of metadata.fcl>

#####
settings.fcl:
#####
<content of settings.fcl>

#####
ranks.fcl:
#####
<content of ranks.fcl>

#####
RunHistory.fcl:
#####
<content of RunHistory.fcl>

#####
RunHistory2.fcl:
#####
<content of RunHistory2.fcl>

End of Record
Run Number: 12345
Packed on Oct 26 14:30 UTC
```

### Blob Format Specification

**Header:**
```
Start of Record
Run Number: <run_number>
Packed on <timestamp>
```
- `<run_number>`: Integer run number
- `<timestamp>`: Format: `MMM DD HH:MM UTC` (e.g., "Oct 26 14:30 UTC")
- Timestamp generated using C locale for consistency

**File Sections:**
```
#####
<relative_filename>:
#####
<file_content>
```
- `<relative_filename>`: Path relative to run directory (e.g., "metadata.fcl" or "subdir/file.fcl")
- `<file_content>`: Complete file content (UTF-8 encoded, binary files converted to ASCII)
- No blank lines between delimiter and content

**Footer:**
```

End of Record
Run Number: <run_number>
Packed on <timestamp>
```
- Preceded by single blank line
- Matches header format

### File Ordering

Files are ordered in the blob as follows:

1. **Regular files** (alphabetically by name, case-insensitive):
   - ComponentConfig.fcl
   - Other .fcl files (alphabetical)

2. **End files** (in specific order):
   - boot.fcl
   - known_boardreaders_list.fcl
   - setup.fcl
   - environment.fcl
   - metadata.fcl
   - settings.fcl
   - ranks.fcl
   - RunHistory.fcl
   - RunHistory2.fcl

**Rationale:** End files appear last because they provide summary and metadata information that may reference other files.

### Blob Creation Implementation

```python
from run_record_archiver.services.blob_creator import BlobCreator

creator = BlobCreator()
blob_text = creator.create_blob_from_directory(
    run_number=12345,
    source_dir=Path("/path/to/exported/run")
)
```

### Blob Extraction Implementation

```python
# Extract files from blob back to directory structure
extracted_files = creator.extract_files_from_blob(
    blob=blob_text,
    output_dir=Path("/path/to/output")
)
# Returns: {"filename": Path, ...}
```

### Blob Validation

Blobs can be validated by comparing MD5 hashes:

```python
from run_record_archiver.services.blob_validator import BlobValidator

validator = BlobValidator()
is_valid = validator.validate_blob(
    original_blob=blob_text,
    retrieved_blob=downloaded_blob_text
)
```

**Validation checks:**
- MD5 hash comparison of blob content
- Ensures no data corruption during upload/download
- Used when `--validate` flag is specified

### Blob Metadata

UconDB stores additional metadata for each blob:

- **Folder:** Organizational namespace (e.g., "run_records")
- **Object:** Object type (e.g., "configuration")
- **Key:** Run number (e.g., "12345")
- **Version:** Auto-generated version identifier (e.g., "v1")
- **MD5 Hash:** Content hash for integrity verification

---

## Lock Files

### Lock File Format

**File:** Specified by `app.lock_file` in config (e.g., `.archiver.lock`)

**Format:** Plain text with single line

**Purpose:** Prevent concurrent archiver instances

**Structure:**
```
<process_id>
```

**Example:**
```
12345
```

### Lock Mechanism

**Implementation:** POSIX file locking using `fcntl.flock()`

**Lock Type:** Exclusive lock (`LOCK_EX`) with non-blocking mode (`LOCK_NB`)

**Lock Lifecycle:**

1. **Acquisition:**
   ```python
   with FileLock(lock_file) as lock:
       # Archiver has exclusive access
       run_pipeline()
   ```

2. **Lock File Content:**
   - Contains PID of holding process
   - Written immediately after acquiring lock
   - Used for lock monitoring and diagnostics

3. **Release:**
   - Automatic on context manager exit
   - Releases `fcntl` lock
   - Lock file remains on disk (deleted on next acquisition)

### Lock Monitoring

The archiver monitors lock file validity during execution:

```python
if not lock.is_lock_file_valid():
    # Lock file was removed externally
    # Trigger graceful shutdown
    logger.warning("Lock file removed, shutting down")
    shutdown()
```

**Validation checks:**
- Lock file still exists
- Lock file contains correct PID
- Checked periodically during long-running operations

### Lock File Removal

**Manual Removal:**
```bash
# Remove stale lock (only if archiver is not running)
rm /path/to/.archiver.lock
```

**Automatic Removal:**
- Not automatically removed on exit (prevents race conditions)
- Overwritten on next archiver start
- If process crashes, lock remains (manual cleanup required)

**Best Practice:**
Check for running process before removing lock:
```bash
# Read PID from lock file
PID=$(cat /path/to/.archiver.lock)

# Check if process exists
if ps -p $PID > /dev/null; then
    echo "Archiver is still running (PID: $PID)"
else
    echo "Stale lock, safe to remove"
    rm /path/to/.archiver.lock
fi
```

### Lock Error Handling

**Error:** Lock already held by another process

**Exception:** `LockExistsError`

**Message:**
```
Another process may be running. Lock file '/path/to/.archiver.lock' is held.
```

**Resolution:**
1. Check if another archiver instance is running
2. If not, manually remove lock file
3. Restart archiver

---

## File Permissions

### Recommended Permissions

```bash
# Configuration files (read-only for archiver)
chmod 640 config.yaml
chmod 600 archiver.env  # Contains passwords

# State files (read-write for archiver)
chmod 644 importer_state.json
chmod 644 migrator_state.json

# Failure logs (read-write for archiver)
chmod 644 import_failures.log
chmod 644 migrate_failures.log

# Lock file (read-write for archiver)
chmod 644 .archiver.lock

# Log files (read-write for archiver, readable by others)
chmod 644 archiver.log
chmod 644 archiver.log.*

# Working directory (read-write-execute for archiver)
chmod 755 /path/to/work_dir
```

### Ownership

All files should be owned by the archiver service user:
```bash
chown archiver:archiver /path/to/work_dir/*
```

---

## File Encoding

All text files use UTF-8 encoding:

- **Configuration files:** UTF-8 with BOM optional
- **State files (JSON):** UTF-8 without BOM
- **Failure logs:** UTF-8 or ASCII
- **Log files:** UTF-8
- **FHiCL files:** UTF-8
- **Blob files:** UTF-8

**Non-UTF-8 Handling:**
- Binary files converted to ASCII (ignore errors)
- Non-ASCII characters cleaned from certain fields
- Locale set to `en_US.UTF-8` for consistent output

---

## File Size Limits

### Recommended Limits

- **config.yaml:** < 100 KB
- **State files:** < 10 KB (typically 1-2 KB)
- **Failure logs:** < 1 MB (typically 1-10 KB)
- **Lock files:** < 1 KB
- **Log files:** 500 MB (auto-rotated)
- **Individual FHiCL files:** < 10 MB
- **Blob files:** < 50 MB (typical: 1-5 MB)

### Large File Handling

If FHiCL files exceed expected sizes:
1. Check for incorrect file inclusion
2. Verify source data quality
3. Consider file size limits in artdaqDB and UconDB

If blobs exceed UconDB limits:
1. Check UconDB server configuration
2. Contact UconDB administrators
3. Consider splitting large configurations

---

## Backup and Recovery

### State Files

**Backup Strategy:**
```bash
# Automatic backup before state updates
cp importer_state.json importer_state.json.bak

# Manual backup
tar czf state_backup_$(date +%Y%m%d).tar.gz \
    importer_state.json \
    migrator_state.json \
    import_failures.log \
    migrate_failures.log
```

**Recovery:**
```bash
# Restore from backup
cp importer_state.json.bak importer_state.json

# Or rebuild from databases
./run_archiver.sh config.yaml --recover-import-state
./run_archiver.sh config.yaml --recover-migrate-state
```

### Configuration Files

**Version Control:**
```bash
# Track configuration in git
git add config.yaml
git commit -m "Update configuration"

# Review history
git log config.yaml
```

### Log Files

**Archival:**
```bash
# Compress old logs
gzip archiver.log.5

# Archive to long-term storage
tar czf logs_archive_$(date +%Y%m).tar.gz archiver.log.*
mv logs_archive_*.tar.gz /path/to/archive/
```

---

## File Validation

### Configuration Validation

Run archiver with `--help` or try a dry run:
```bash
# Test configuration parsing
./run_archiver.sh config.yaml --report-status
```

### State File Validation

Check JSON syntax:
```bash
# Validate JSON
python3 -m json.tool importer_state.json
```

Expected format:
```json
{
  "last_contiguous_run": 12345,
  "last_attempted_run": 12350
}
```

### Failure Log Validation

Check format:
```bash
# Should contain only integers, one per line
grep -v '^[0-9]\+$' import_failures.log
# (No output = valid format)
```

### FHiCL Validation

Use artdaq_database tools:
```bash
# Validate FHiCL syntax
fhicl-dump file.fcl

# Expand FHiCL includes
fhicl-expand file.fcl
```

---

## Troubleshooting

### Common File Issues

**Issue:** State file corrupted
```bash
# Symptom: JSON parse error
# Solution: Rebuild state
./run_archiver.sh config.yaml --recover-import-state
```

**Issue:** Lock file won't release
```bash
# Symptom: "Lock file is held" error
# Check if process is running
ps aux | grep run_record_archiver
# If not running, remove lock
rm .archiver.lock
```

**Issue:** Log file not rotating
```bash
# Check log file size
ls -lh archiver.log
# Check permissions
ls -l archiver.log*
# Should see archiver.log.1, .2, etc.
```

**Issue:** Configuration not loading
```bash
# Check YAML syntax
python3 -c "import yaml; yaml.safe_load(open('config.yaml'))"
# Check environment variables
env | grep -E 'WORK_DIR|ARTDAQDB|UCONDB'
```

---

## File Format Version History

**Version 1.0** (Current)
- Initial file format specifications
- Support for state tracking with dual fields (last_contiguous_run, last_attempted_run)
- Blob format with ordered file sections
- Log rotation with size and age limits

**Future Considerations:**
- State file format versioning
- Compressed blob storage
- Encrypted configuration files
- Extended metadata in state files

---

## Related Documentation

- **Configuration Guide:** `~/run_record_archiver/run_record_archiver/config.md`
- **Main Documentation:** `~/run_record_archiver/CLAUDE.md`
- **Build Guide:** `~/run_record_archiver/run_record_archiver/build.md`
- **Developer Guide:** `~/run_record_archiver/DEVELOPER_GUIDE.md`
