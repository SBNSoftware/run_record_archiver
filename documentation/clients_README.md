# Clients Package Documentation

## Overview

The `clients` package provides interface implementations for external systems used by the Run Record Archiver. Each client encapsulates communication with a specific external service, handling connection management, error handling, and performance monitoring.

**Available Clients:**
- **ArtdaqDBClient**: Interface to intermediate artdaqDB (MongoDB/FilesystemDB) for temporary storage
- **UconDBClient**: Interface to destination UconDB server for long-term versioned storage
- **CarbonClient**: Optional interface to Carbon/Graphite metrics server for performance monitoring

**Common Features:**
- Performance monitoring via `@performance_monitor` decorator
- Carbon metrics integration for tracking operation duration
- Fuzzing/testing capabilities for simulating failures
- Comprehensive error handling with custom exceptions
- Configurable via YAML configuration file

**Package Structure:**
```
run_record_archiver/clients/
├── __init__.py
├── artdaq.py      # ArtdaqDBClient - intermediate database operations
├── ucondb.py      # UconDBClient - destination database operations
└── carbon.py      # CarbonClient - metrics reporting
```

---

## ArtdaqDBClient

**Module:** `run_record_archiver.clients.artdaq`

### Purpose

The `ArtdaqDBClient` provides an interface to the intermediate artdaqDB, which temporarily stores run configurations during the import stage before migration to UconDB. It supports two operational modes:

1. **Python API (conftoolp)**: Direct database operations using the artdaq_database library
2. **CLI Tools (bulkloader/bulkdownloader)**: High-performance command-line tools with optional remote execution via SSH

### Class Definition

```python
class ArtdaqDBClient:
    """Client for artdaqDB operations (MongoDB/FilesystemDB)."""
```

### Constructor

```python
def __init__(
    self,
    database_uri: str,
    use_tools: bool,
    remote_host: Optional[str],
    carbon_client: Optional[CarbonClient] = None,
    random_skip_percent: int = 0,
    random_error_percent: int = 0,
    random_skip_retry: bool = False,
    random_error_retry: bool = False,
)
```

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `database_uri` | `str` | Yes | - | Connection URI for artdaqDB (e.g., `mongodb://host/database_archive`) |
| `use_tools` | `bool` | Yes | - | If `True`, use CLI tools (bulkloader/bulkdownloader); if `False`, use conftoolp API |
| `remote_host` | `Optional[str]` | No | `None` | Optional remote host for CLI tool execution via SSH |
| `carbon_client` | `Optional[CarbonClient]` | No | `None` | Optional Carbon metrics client for performance monitoring |
| `random_skip_percent` | `int` | No | `0` | Percentage of runs to randomly skip (0-100, for testing) |
| `random_error_percent` | `int` | No | `0` | Percentage of runs to randomly fail (0-100, for testing) |
| `random_skip_retry` | `bool` | No | `False` | If `True`, skipped runs raise `FuzzSkipError` (permanent failure) |
| `random_error_retry` | `bool` | No | `False` | If `True`, errored runs raise `FuzzSkipError` (permanent failure) |

**Initialization Behavior:**
- Initializes `conftoolp` library (sets locale, enables tracing)
- Checks for `ARTDAQ_DATABASE_REMOTEHOST` environment variable if `remote_host` not provided
- Stores configuration for later use in operations

### Public Methods

#### `get_archived_runs() -> Set[int]`

Query artdaqDB for all runs that have been imported.

**Returns:**
- `Set[int]`: Set of run numbers that exist in artdaqDB

**Raises:**
- `ArtdaqDBError`: If query fails or response parsing fails

**Performance:**
- Decorated with `@performance_monitor` (reports metrics to Carbon if enabled)

**Example:**
```python
client = ArtdaqDBClient(
    database_uri="mongodb://localhost/artdaq_database_archive",
    use_tools=False,
    remote_host=None
)
archived_runs = client.get_archived_runs()
print(f"Found {len(archived_runs)} archived runs")
# Output: Found 1523 archived runs
```

---

#### `get_configuration_name(run_number: int) -> str`

Get the exact configuration name for a specific run.

**Parameters:**
- `run_number` (`int`): Run number to query

**Returns:**
- `str`: Full configuration name including run number prefix (e.g., `"12345/ConfigName"`)

**Raises:**
- `ArtdaqDBError`: If configuration not found or query fails

**Important Notes:**
- Returns full name with run number prefix for `conftoolp` API: `"12345/ConfigName"`
- For `bulkdownloader`, the run number prefix is stripped: `"ConfigName"`
- This ensures precise exports without wildcard matching issues

**Example:**
```python
config_name = client.get_configuration_name(12345)
print(config_name)
# Output: "12345/standard"

# The archiver uses this to get the exact name before exporting
if "/" in config_name:
    config_name_only = config_name.split("/", 1)[1]  # "standard"
```

---

#### `archive_run(run_number: int, config_name: str, prepared_fcl_dir: Path, update: bool) -> None`

Import a run configuration into artdaqDB (two-step process).

**Parameters:**
- `run_number` (`int`): Run number to archive
- `config_name` (`str`): Configuration name (e.g., `"standard"`)
- `prepared_fcl_dir` (`Path`): Directory containing prepared FHiCL files
- `update` (`bool`): If `False`, perform initial insert; if `True`, perform update (add stop-time)

**Returns:**
- `None`

**Raises:**
- `ArtdaqDBError`: If import fails, configuration already exists (when `update=False`), or configuration not found (when `update=True`)
- `FuzzSkipError`: If fuzzing is enabled and run is permanently skipped (testing only)

**Performance:**
- Decorated with `@performance_monitor`

**Two-Step Process:**
1. **Initial Insert** (`update=False`): Loads main configuration files into artdaqDB
2. **Stop-time Update** (`update=True`): Adds stop-time metadata via update operation

**Fuzzing Behavior (Testing Only):**
- Disabled when `incremental_mode=True` or `update=True`
- Random skip: Silently returns (if `random_skip_retry=False`) or raises `FuzzSkipError` (if `random_skip_retry=True`)
- Random error: 50% chance to raise `ArtdaqDBError` (if `random_error_retry=False`) or `FuzzSkipError` (if `random_error_retry=True`)

**Example:**
```python
from pathlib import Path

# Initial insert
client.archive_run(
    run_number=12345,
    config_name="standard",
    prepared_fcl_dir=Path("/tmp/run_12345/initial"),
    update=False
)

# Update with stop-time
client.archive_run(
    run_number=12345,
    config_name="standard",
    prepared_fcl_dir=Path("/tmp/run_12345/update"),
    update=True
)
```

---

#### `export_run_configuration(run_number: int, destination_dir: Path) -> None`

Export a run configuration from artdaqDB to filesystem.

**Parameters:**
- `run_number` (`int`): Run number to export
- `destination_dir` (`Path`): Directory where exported FHiCL files will be written

**Returns:**
- `None`

**Raises:**
- `ArtdaqDBError`: If export fails, configuration not found, or file I/O fails

**Performance:**
- Decorated with `@performance_monitor`

**Behavior:**
1. Calls `get_configuration_name()` to get exact config name
2. Strips run number prefix for `bulkdownloader` (keeps full name for `conftoolp`)
3. Exports all FHiCL files to `destination_dir`
4. Each entity is written as `{entity_name}.fcl`

**Example:**
```python
from pathlib import Path

export_dir = Path("/tmp/exported_runs/run_12345")
export_dir.mkdir(parents=True, exist_ok=True)

client.export_run_configuration(12345, export_dir)

# Result: /tmp/exported_runs/run_12345/
#   ├── schema.fcl
#   ├── boot.fcl
#   ├── metadata.fcl
#   ├── RunHistory.fcl
#   └── ...
```

---

#### `set_incremental_mode(incremental: bool) -> None`

Set incremental mode flag to disable random testing features.

**Parameters:**
- `incremental` (`bool`): If `True`, disables fuzzing; if `False`, enables fuzzing (if configured)

**Returns:**
- `None`

**Example:**
```python
# Disable fuzzing when running in incremental mode
client.set_incremental_mode(True)
```

---

### Configuration

**YAML Section:** `artdaq_db`

```yaml
artdaq_db:
  database_uri: "mongodb://dbhost:27017/artdaq_database_archive"
  use_tools: false                  # true = CLI tools, false = conftoolp API
  remote_host: null                 # Optional: "user@remotehost" for SSH execution
  fcl_conf_dir: "/path/to/schema"   # Schema directory for FHiCL preparation
```

**Environment Variables:**
- `ARTDAQ_DATABASE_URI`: Set temporarily during operations (overridden by config)
- `ARTDAQ_DATABASE_REMOTEHOST`: Fallback for `remote_host` if not specified in config

---

### Error Handling

**Exceptions Raised:**

| Exception | Scenario |
|-----------|----------|
| `ArtdaqDBError` | Database connection failure, query failure, import/export errors, configuration not found |
| `FuzzSkipError` | Testing mode: permanent skip/error (when `random_*_retry=True`) |
| `ImportError` | `conftoolp` module not available |

**Error Context:**
All `ArtdaqDBError` exceptions include:
- Stage information (e.g., `"Import"`, `"Migration"`)
- Run number (if applicable)
- Detailed error message from underlying library

---

### Usage Examples

#### Basic Import and Export

```python
from run_record_archiver.clients.artdaq import ArtdaqDBClient
from pathlib import Path

# Initialize client
client = ArtdaqDBClient(
    database_uri="mongodb://localhost/artdaq_database_archive",
    use_tools=False,
    remote_host=None
)

# Check what's already archived
archived_runs = client.get_archived_runs()
print(f"Archived runs: {sorted(archived_runs)[:10]}...")

# Archive a new run (two-step process)
run_number = 12345
config_name = "standard"
prepared_dir = Path("/tmp/prepared_12345")

# Step 1: Initial insert
client.archive_run(run_number, config_name, prepared_dir / "initial", update=False)

# Step 2: Add stop-time
client.archive_run(run_number, config_name, prepared_dir / "update", update=True)

# Export the run
export_dir = Path("/tmp/exported_12345")
export_dir.mkdir(parents=True, exist_ok=True)
client.export_run_configuration(run_number, export_dir)
```

#### Using CLI Tools with Remote Host

```python
# Use bulkloader/bulkdownloader on remote host
client = ArtdaqDBClient(
    database_uri="filesystemdb:///data/artdaq_database",
    use_tools=True,
    remote_host="user@artdaq-server.example.com"
)

# Operations use SSH tar-pipe for data transfer
client.archive_run(12345, "standard", prepared_dir, update=False)
client.export_run_configuration(12345, export_dir)
```

#### With Metrics Reporting

```python
from run_record_archiver.clients.carbon import CarbonClient

# Initialize Carbon client
carbon = CarbonClient(
    host="carbon.example.com",
    port=2003,
    metric_prefix="exp.run_archiver.prod",
    enabled=True
)

# Pass to ArtdaqDBClient
client = ArtdaqDBClient(
    database_uri="mongodb://localhost/artdaq_database_archive",
    use_tools=False,
    remote_host=None,
    carbon_client=carbon
)

# All operations are automatically timed and reported
client.get_archived_runs()
# Posts metric: exp.run_archiver.prod.get_archived_runs.duration_ms 123.45
```

#### Testing with Fuzzing

```python
# Enable fuzzing for testing (10% skip rate, 5% error rate)
client = ArtdaqDBClient(
    database_uri="mongodb://localhost/artdaq_database_archive",
    use_tools=False,
    remote_host=None,
    random_skip_percent=10,
    random_error_percent=5,
    random_skip_retry=False,  # Skipped runs will retry
    random_error_retry=False  # Errored runs will retry
)

# Some runs will randomly skip or fail (for testing retry logic)
for run_num in range(100, 200):
    try:
        client.archive_run(run_num, "standard", prepared_dir, update=False)
    except ArtdaqDBError as e:
        print(f"Run {run_num} failed: {e}")
```

---

## UconDBClient

**Module:** `run_record_archiver.clients.ucondb`

### Purpose

The `UconDBClient` provides an interface to the destination UconDB server, which stores run configurations as versioned text blobs for long-term archival. It wraps the `ucondb.webapi.UConDBClient` library with simplified operations for run record management.

### Class Definition

```python
class UconDBClient:
    """Client for UconDB REST API operations."""
```

### Constructor

```python
def __init__(
    self,
    config: UconDBConfig,
    carbon_client: Optional[CarbonClient] = None,
    random_skip_percent: int = 0,
    random_error_percent: int = 0,
    random_skip_retry: bool = False,
    random_error_retry: bool = False,
)
```

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `config` | `UconDBConfig` | Yes | - | UconDB configuration object (from `config.ucon_db`) |
| `carbon_client` | `Optional[CarbonClient]` | No | `None` | Optional Carbon metrics client for performance monitoring |
| `random_skip_percent` | `int` | No | `0` | Percentage of runs to randomly skip (0-100, for testing) |
| `random_error_percent` | `int` | No | `0` | Percentage of runs to randomly fail (0-100, for testing) |
| `random_skip_retry` | `bool` | No | `False` | If `True`, skipped runs raise `FuzzSkipError` (permanent failure) |
| `random_error_retry` | `bool` | No | `False` | If `True`, errored runs raise `FuzzSkipError` (permanent failure) |

**Initialization Behavior:**
- Disables SSL warnings (via `urllib3.disable_warnings()`)
- Initializes underlying `ucondb.webapi.UConDBClient`
- Tests connection by calling `client.version()`
- Logs successful connection with server version

### Public Methods

#### `get_existing_runs() -> Set[int]`

Query UconDB for all runs that have been migrated.

**Returns:**
- `Set[int]`: Set of run numbers that exist in UconDB

**Raises:**
- `UconDBError`: If query fails or response parsing fails

**Performance:**
- Decorated with `@performance_monitor`

**Example:**
```python
client = UconDBClient(config.ucon_db)
existing_runs = client.get_existing_runs()
print(f"Found {len(existing_runs)} runs in UconDB")
# Output: Found 2847 runs in UconDB
```

---

#### `upload_blob(run_number: int, blob_content: str) -> str`

Upload a run configuration blob to UconDB.

**Parameters:**
- `run_number` (`int`): Run number (used as key)
- `blob_content` (`str`): Concatenated FHiCL configuration text

**Returns:**
- `str`: Version identifier assigned by UconDB (e.g., `"v1"`, `"v2"`, etc.)

**Raises:**
- `UconDBError`: If upload fails
- `FuzzSkipError`: If fuzzing is enabled and run is permanently skipped (testing only)

**Performance:**
- Decorated with `@performance_monitor`

**Special Handling:**
- If run already exists, logs warning and returns placeholder version (`"existing_{run_number}"`)
- This allows idempotent uploads (re-uploading same run doesn't fail)

**Fuzzing Behavior (Testing Only):**
- Disabled when `incremental_mode=True`
- Random skip: Returns fake version (if `random_skip_retry=False`) or raises `FuzzSkipError` (if `random_skip_retry=True`)
- Random error: 50% chance to raise `UconDBError` (if `random_error_retry=False`) or `FuzzSkipError` (if `random_error_retry=True`)

**Example:**
```python
blob_content = """
# Run 12345 Configuration
boot.fcl: {...}
metadata.fcl: {...}
"""

version = client.upload_blob(12345, blob_content)
print(f"Uploaded run 12345 as version: {version}")
# Output: Uploaded run 12345 as version: v1
```

---

#### `get_data(run_number: int) -> str`

Download blob data for a specific run from UconDB.

**Parameters:**
- `run_number` (`int`): Run number to download

**Returns:**
- `str`: Blob content as string

**Raises:**
- `UconDBError`: If download fails or run doesn't exist

**Performance:**
- Decorated with `@performance_monitor`

**Example:**
```python
blob_content = client.get_data(12345)
print(f"Downloaded {len(blob_content)} bytes for run 12345")
# Output: Downloaded 45678 bytes for run 12345
```

---

#### `set_incremental_mode(incremental: bool) -> None`

Set incremental mode flag to disable random testing features.

**Parameters:**
- `incremental` (`bool`): If `True`, disables fuzzing; if `False`, enables fuzzing (if configured)

**Returns:**
- `None`

**Example:**
```python
client.set_incremental_mode(True)
```

---

### Configuration

**YAML Section:** `ucon_db`

```yaml
ucon_db:
  server_url: "https://ucondb.example.com:8443/ucondb"
  folder_name: "run_records"
  object_name: "configuration"
  writer_user: "archiver_bot"
  writer_password: "${UCONDB_WRITER_PASSWORD}"  # Use env var
  timeout_seconds: 10
```

**Configuration Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `server_url` | `str` | Yes | - | UconDB server URL with protocol and port |
| `folder_name` | `str` | Yes | - | Folder name in UconDB (organizational namespace) |
| `object_name` | `str` | Yes | - | Object type within folder |
| `writer_user` | `str` | Yes | - | Username for write operations |
| `writer_password` | `str` | Yes | - | Password for write operations |
| `timeout_seconds` | `int` | No | `10` | HTTP request timeout in seconds |

---

### Error Handling

**Exceptions Raised:**

| Exception | Scenario |
|-----------|----------|
| `UconDBError` | Server connection failure, authentication failure, upload/download errors, run not found |
| `FuzzSkipError` | Testing mode: permanent skip/error (when `random_*_retry=True`) |

**Error Context:**
All `UconDBError` exceptions include:
- Stage information (e.g., `"Migration"`)
- Run number (if applicable)
- Detailed error message from HTTP response

---

### Usage Examples

#### Basic Upload and Download

```python
from run_record_archiver.clients.ucondb import UconDBClient

# Initialize client
client = UconDBClient(config.ucon_db)

# Check what's already in UconDB
existing_runs = client.get_existing_runs()
print(f"Existing runs: {len(existing_runs)}")

# Upload a new run
blob_content = """
# Run 12345 Configuration
boot.fcl: {...}
metadata.fcl: {...}
RunHistory.fcl: {...}
"""

version = client.upload_blob(12345, blob_content)
print(f"Uploaded as version: {version}")

# Download it back
downloaded = client.get_data(12345)
assert downloaded == blob_content
```

#### With Metrics Reporting

```python
from run_record_archiver.clients.carbon import CarbonClient

carbon = CarbonClient(
    host="carbon.example.com",
    port=2003,
    metric_prefix="exp.run_archiver.prod",
    enabled=True
)

client = UconDBClient(config.ucon_db, carbon_client=carbon)

# All operations are automatically timed
client.upload_blob(12345, blob_content)
# Posts metric: exp.run_archiver.prod.upload_blob.duration_ms 234.56
```

#### Handling Existing Runs

```python
# Upload will succeed even if run already exists
try:
    version = client.upload_blob(12345, blob_content)
    if version.startswith("existing_"):
        print("Run already exists in UconDB")
    else:
        print(f"New upload: {version}")
except UconDBError as e:
    print(f"Upload failed: {e}")
```

---

## CarbonClient

**Module:** `run_record_archiver.clients.carbon`

### Purpose

The `CarbonClient` provides an interface to a Carbon/Graphite metrics server for posting performance metrics. It supports the plaintext protocol and is used by the `@performance_monitor` decorator to track operation duration.

### Class Definition

```python
class CarbonClient:
    """Client for posting metrics to Carbon/Graphite server."""
```

### Constructor

```python
def __init__(
    self,
    host: Optional[str] = None,
    port: Optional[int] = None,
    metric_prefix: Optional[str] = None,
    enabled: bool = False,
)
```

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `host` | `Optional[str]` | No | `None` | Carbon server hostname |
| `port` | `Optional[int]` | No | `2003` | Carbon server port (default: 2003) |
| `metric_prefix` | `Optional[str]` | No | `None` | Prefix prepended to all metric paths |
| `enabled` | `bool` | No | `False` | Whether metrics posting is enabled |

**Initialization Behavior:**
- If `enabled=True` but `host`, `port`, or `metric_prefix` is missing, logs warning and disables client
- No connection is established during initialization (metrics are sent on-demand)

### Public Methods

#### `post_metric(metric_path: str, value: float, timestamp: Optional[float] = None) -> None`

Post a metric to Carbon/Graphite server.

**Parameters:**
- `metric_path` (`str`): Metric path (will be prefixed with `metric_prefix`)
- `value` (`float`): Metric value
- `timestamp` (`Optional[float]`): Unix timestamp (defaults to current time)

**Returns:**
- `None`

**Behavior:**
- If `enabled=False`, returns immediately without sending
- Opens TCP socket connection to Carbon server
- Sends metric in plaintext format: `{prefix}.{path} {value} {timestamp}\n`
- Closes connection
- If connection fails, logs warning and continues (non-blocking)

**Example:**
```python
from run_record_archiver.clients.carbon import CarbonClient
import time

client = CarbonClient(
    host="carbon.example.com",
    port=2003,
    metric_prefix="exp.run_archiver.prod",
    enabled=True
)

# Post a metric
client.post_metric("import.runs_processed", 42)
# Sends: "exp.run_archiver.prod.import.runs_processed 42 <timestamp>\n"

# Post with custom timestamp
client.post_metric("migrate.duration_ms", 1234.5, timestamp=time.time())
```

---

### Configuration

**YAML Section:** `carbon`

```yaml
carbon:
  enabled: true
  host: "carbon.example.com"
  port: 2003
  metric_prefix: "exp.run_archiver.prod"
```

**Configuration Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `enabled` | `bool` | No | `false` | Enable/disable metrics posting |
| `host` | `str` | Yes (if enabled) | - | Carbon server hostname |
| `port` | `int` | No | `2003` | Carbon server port |
| `metric_prefix` | `str` | Yes (if enabled) | - | Metric namespace prefix |

---

### Error Handling

**Exceptions Raised:**
- **None** - All errors are caught and logged as warnings

**Error Scenarios:**
- Socket connection failure → logs warning, continues
- Socket timeout → logs warning, continues
- Missing configuration → logs warning, disables client

This non-blocking design ensures metrics failures never interrupt archiver operations.

---

### Usage Examples

#### Basic Metrics Posting

```python
client = CarbonClient(
    host="carbon.example.com",
    port=2003,
    metric_prefix="app.archiver",
    enabled=True
)

# Post various metrics
client.post_metric("runs.imported", 15)
client.post_metric("runs.migrated", 14)
client.post_metric("runs.failed", 1)
client.post_metric("duration.import_ms", 5432.1)
```

#### With Performance Monitor Decorator

The `@performance_monitor` decorator automatically uses the Carbon client:

```python
from run_record_archiver.utils import performance_monitor

carbon = CarbonClient(host="carbon.example.com", port=2003, 
                     metric_prefix="exp.archiver", enabled=True)

class MyService:
    def __init__(self):
        self.carbon_client = carbon
    
    @performance_monitor
    def expensive_operation(self):
        # Do work...
        pass

# Automatically posts metric: exp.archiver.expensive_operation.duration_ms
```

#### Disabled Client (No-Op)

```python
# Create disabled client for development
client = CarbonClient(enabled=False)

# All post_metric calls are no-ops
client.post_metric("test.metric", 123)  # Does nothing
```

---

## Common Client Patterns

### Initialization from Config

All clients are initialized by the Orchestrator from YAML configuration:

```python
from run_record_archiver.config import Config
from run_record_archiver.clients.artdaq import ArtdaqDBClient
from run_record_archiver.clients.ucondb import UconDBClient
from run_record_archiver.clients.carbon import CarbonClient

# Load configuration
config = Config.from_file("config.yaml")

# Initialize Carbon client first (used by other clients)
carbon_client = CarbonClient(
    host=config.carbon.host,
    port=config.carbon.port,
    metric_prefix=config.carbon.metric_prefix,
    enabled=config.carbon.enabled,
)

# Initialize ArtdaqDB client with Carbon integration
artdaq_client = ArtdaqDBClient(
    database_uri=config.artdaq_db.database_uri,
    use_tools=config.artdaq_db.use_tools,
    remote_host=config.artdaq_db.remote_host,
    carbon_client=carbon_client,
    random_skip_percent=config.app_fuzz.random_skip_percent,
    random_error_percent=config.app_fuzz.random_error_percent,
    random_skip_retry=config.app_fuzz.random_skip_retry,
    random_error_retry=config.app_fuzz.random_error_retry,
)

# Initialize UconDB client with Carbon integration
ucon_client = UconDBClient(
    config.ucon_db,
    carbon_client,
    random_skip_percent=config.app_fuzz.random_skip_percent,
    random_error_percent=config.app_fuzz.random_error_percent,
    random_skip_retry=config.app_fuzz.random_skip_retry,
    random_error_retry=config.app_fuzz.random_error_retry,
)
```

---

### Performance Monitoring Pattern

All database operations are decorated with `@performance_monitor`:

```python
from run_record_archiver.utils import performance_monitor

class ArtdaqDBClient:
    @performance_monitor
    def get_archived_runs(self) -> Set[int]:
        # Implementation...
        pass

# When called, automatically:
# 1. Records start time
# 2. Executes method
# 3. Records end time
# 4. Calculates duration_ms
# 5. Posts metric to Carbon: {prefix}.get_archived_runs.duration_ms
# 6. Logs execution time at DEBUG level
```

---

### Fuzzing/Testing Pattern

Clients support fuzzing for testing failure scenarios:

```python
# Configure fuzzing in config.yaml
app_fuzz:
  random_skip_percent: 10   # 10% of runs randomly skip
  random_error_percent: 5   # 5% of runs randomly error
  random_skip_retry: false  # Skipped runs will retry
  random_error_retry: false # Errored runs will retry

# Fuzzing is automatically disabled in incremental mode
orchestrator.run(incremental=True)  # No fuzzing
orchestrator.run(incremental=False) # Fuzzing enabled
```

**Fuzzing Modes:**

| Mode | `random_*_retry=False` | `random_*_retry=True` |
|------|------------------------|----------------------|
| **Skip** | Silent skip, will retry | Raises `FuzzSkipError`, won't retry |
| **Error** | Raises normal exception, will retry | Raises `FuzzSkipError`, won't retry |

---

### Error Handling Pattern

All clients raise specific exceptions:

```python
from run_record_archiver.exceptions import ArtdaqDBError, UconDBError

try:
    # ArtdaqDB operations
    client.archive_run(run_number, config_name, prepared_dir, update=False)
except ArtdaqDBError as e:
    logger.error("Import failed: %s", e)
    # e.stage = "Import"
    # e.run_number = 12345
    # e.context = {...}

try:
    # UconDB operations
    version = client.upload_blob(run_number, blob_content)
except UconDBError as e:
    logger.error("Upload failed: %s", e)
    # e.stage = "Migration"
    # e.run_number = 12345
```

---

## Integration Points

### Orchestrator

The Orchestrator initializes all clients and passes them to stage components:

```python
class Orchestrator:
    def __init__(self, config: Config):
        # Initialize clients
        self.carbon_client = CarbonClient(...)
        self.artdaq_client = ArtdaqDBClient(...)
        self.ucon_client = UconDBClient(...)
        
        # Pass to stage components
        self.importer = Importer(
            config=config,
            artdaq_client=self.artdaq_client,
            fcl_preparer=...,
            state_manager=...,
        )
        
        self.migrator = Migrator(
            config=config,
            artdaq_client=self.artdaq_client,
            ucon_client=self.ucon_client,
            blob_creator=...,
            state_manager=...,
        )
```

---

### Importer (Import Stage)

The Importer uses `ArtdaqDBClient` to:
1. Query archived runs: `get_archived_runs()`
2. Import new runs: `archive_run()` (two-step)

```python
class Importer:
    def __init__(self, artdaq_client: ArtdaqDBClient, ...):
        self.artdaq_client = artdaq_client
    
    def _get_candidate_runs(self, incremental: bool) -> List[int]:
        # Get runs already in artdaqDB
        archived_runs = self.artdaq_client.get_archived_runs()
        filesystem_runs = self._scan_filesystem()
        # Find new runs
        return [r for r in filesystem_runs if r not in archived_runs]
    
    def _process_run(self, run_number: int) -> bool:
        # Prepare FHiCL files
        prepared_dir = self.fcl_preparer.prepare(run_number, ...)
        
        # Step 1: Initial insert
        self.artdaq_client.archive_run(
            run_number, config_name, prepared_dir / "initial", update=False
        )
        
        # Step 2: Add stop-time
        self.artdaq_client.archive_run(
            run_number, config_name, prepared_dir / "update", update=True
        )
        return True
```

---

### Migrator (Migration Stage)

The Migrator uses both `ArtdaqDBClient` and `UconDBClient`:
1. Query unmigrated runs: `artdaq_client.get_archived_runs()` and `ucon_client.get_existing_runs()`
2. Export from artdaqDB: `artdaq_client.export_run_configuration()`
3. Upload to UconDB: `ucon_client.upload_blob()`

```python
class Migrator:
    def __init__(
        self,
        artdaq_client: ArtdaqDBClient,
        ucon_client: UconDBClient,
        ...
    ):
        self.artdaq_client = artdaq_client
        self.ucon_client = ucon_client
    
    def _get_candidate_runs(self, incremental: bool) -> List[int]:
        # Get runs in artdaqDB but not in UconDB
        archived_runs = self.artdaq_client.get_archived_runs()
        ucon_runs = self.ucon_client.get_existing_runs()
        return [r for r in archived_runs if r not in ucon_runs]
    
    def _process_run(self, run_number: int) -> bool:
        # Export from artdaqDB
        export_dir = Path(f"/tmp/export_{run_number}")
        self.artdaq_client.export_run_configuration(run_number, export_dir)
        
        # Create blob
        blob_content = self.blob_creator.create_blob(export_dir)
        
        # Upload to UconDB
        version = self.ucon_client.upload_blob(run_number, blob_content)
        logger.info("Uploaded run %d as version %s", run_number, version)
        return True
```

---

### Reporter (Status Reporting)

The Reporter uses all clients to generate comprehensive status reports:

```python
class Reporter:
    def __init__(
        self,
        filesystem_client: FilesystemClient,
        artdaq_client: ArtdaqDBClient,
        ucon_client: UconDBClient,
    ):
        self.filesystem_client = filesystem_client
        self.artdaq_client = artdaq_client
        self.ucon_client = ucon_client
    
    def generate_report(self) -> str:
        # Query all three data sources
        filesystem_runs = self.filesystem_client.scan_runs()
        artdaq_runs = self.artdaq_client.get_archived_runs()
        ucon_runs = self.ucon_client.get_existing_runs()
        
        # Analyze differences
        not_imported = filesystem_runs - artdaq_runs
        not_migrated = artdaq_runs - ucon_runs
        
        # Generate report
        return f"""
        Filesystem: {len(filesystem_runs)} runs
        ArtdaqDB:   {len(artdaq_runs)} runs
        UconDB:     {len(ucon_runs)} runs
        
        Not imported: {len(not_imported)} runs
        Not migrated: {len(not_migrated)} runs
        """
```

---

## Testing Considerations

### Mocking Clients

For unit tests, mock clients instead of connecting to real databases:

```python
from unittest.mock import Mock, MagicMock

def test_importer():
    # Mock ArtdaqDB client
    mock_artdaq = Mock(spec=ArtdaqDBClient)
    mock_artdaq.get_archived_runs.return_value = {100, 101, 102}
    mock_artdaq.archive_run.return_value = None
    
    # Test importer logic
    importer = Importer(artdaq_client=mock_artdaq, ...)
    importer.run(incremental=False)
    
    # Verify client was called
    mock_artdaq.get_archived_runs.assert_called_once()
    assert mock_artdaq.archive_run.call_count > 0
```

---

### Integration Tests

For integration tests, use `tests_config.yaml` to control test mode:

```yaml
# tests_config.yaml
tests:
  test_clients_artdaq: true   # Use real conftoolp and artdaqDB
  test_clients_ucondb: true   # Use real UconDB server
  test_importer: mock         # Use mock conftoolp
```

```python
# tests/test_clients_artdaq.py
import pytest
from test_helpers import should_use_mocks

@pytest.mark.skipif(should_use_mocks(), reason="Requires real artdaqDB")
def test_real_artdaq_operations():
    # Test with real database
    client = ArtdaqDBClient(...)
    runs = client.get_archived_runs()
    assert len(runs) > 0
```

---

### Fuzzing Tests

Test retry logic using fuzzing parameters:

```python
def test_retry_on_random_errors():
    client = ArtdaqDBClient(
        database_uri="...",
        use_tools=False,
        remote_host=None,
        random_error_percent=50,  # 50% error rate
        random_error_retry=False  # Allow retries
    )
    
    # Some runs will fail, some will succeed
    successes = 0
    failures = 0
    for run_num in range(100, 200):
        try:
            client.archive_run(run_num, "standard", prepared_dir, update=False)
            successes += 1
        except ArtdaqDBError:
            failures += 1
    
    # Approximately 50% failure rate
    assert 40 <= failures <= 60
```

---

## Summary

The clients package provides:

- **ArtdaqDBClient**: Intermediate database operations (import, export, query)
- **UconDBClient**: Destination database operations (upload, download, query)
- **CarbonClient**: Optional performance metrics reporting

**Key Design Principles:**
- Separation of concerns (each client handles one external system)
- Performance monitoring via decorators
- Comprehensive error handling with custom exceptions
- Testing support via fuzzing and mocking
- Configuration-driven initialization

**Integration:**
- Orchestrator initializes all clients
- Importer uses ArtdaqDBClient
- Migrator uses ArtdaqDBClient + UconDBClient
- Reporter uses all clients

**Best Practices:**
- Always pass Carbon client to enable metrics
- Use fuzzing only for testing (disable in production)
- Handle exceptions at appropriate levels
- Mock clients in unit tests
- Use integration tests with real databases when needed
