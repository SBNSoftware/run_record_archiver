# Persistence Package

The `persistence` package provides state management and file locking functionality for the Run Record Archiver. It handles tracking of processed runs, failure logging, and prevents concurrent execution through file-based locking.

## Package Overview

The persistence package consists of two modules:

- **`state.py`**: State management functions for tracking processed runs and failures
- **`lock.py`**: File-based locking mechanism to prevent concurrent archiver instances

## Module: state.py

The state module manages JSON-based state files that track:
- Last contiguous successful run number
- Last attempted run number
- Failed run numbers (in separate failure log files)

### Core Functions

#### read_state(state_file: Path) -> Dict[str, Any]

Reads state from a JSON file. Returns empty dict if file doesn't exist or is corrupted.

**Parameters:**
- `state_file`: Path to the JSON state file

**Returns:**
- Dictionary containing state data (empty dict if read fails)

**Example:**
```python
from pathlib import Path
from run_record_archiver.persistence import state

state_file = Path("/var/run_record_archiver/import_state.json")
current_state = state.read_state(state_file)
print(current_state)
# Output: {'last_contiguous_run': 19500, 'last_attempted_run': 19550}
```

#### write_state(state_file: Path, state: Dict[str, Any]) -> bool

Writes state dictionary to a JSON file. Creates parent directories if needed.

**Parameters:**
- `state_file`: Path to the JSON state file
- `state`: Dictionary to write

**Returns:**
- `True` if write succeeded, `False` otherwise

**Example:**
```python
state_data = {
    'last_contiguous_run': 19500,
    'last_attempted_run': 19550,
    'timestamp': '2025-10-24T10:30:00'
}
success = state.write_state(state_file, state_data)
if success:
    print("State saved successfully")
```

#### update_contiguous_run_state(state_file: Path, successful_runs: List[int]) -> None

Updates the `last_contiguous_run` value based on successfully processed runs. Only updates if the new runs extend the contiguous sequence from the current last run.

**Key Behavior:**
- Only advances if runs are consecutive (no gaps)
- Stops at first gap in sequence
- Ensures no gaps when failures occur

**Parameters:**
- `state_file`: Path to the JSON state file
- `successful_runs`: List of run numbers that succeeded (order doesn't matter)

**Example:**
```python
# Current state: last_contiguous_run = 100
state.update_contiguous_run_state(state_file, [101, 102, 103])
# Result: last_contiguous_run = 103

# Current state: last_contiguous_run = 103
state.update_contiguous_run_state(state_file, [104, 106, 107])
# Result: last_contiguous_run = 104 (stops at gap before 106)

# Current state: last_contiguous_run = 104
state.update_contiguous_run_state(state_file, [107, 108, 109])
# Result: last_contiguous_run = 104 (no change, gap at 105-106)
```

#### update_attempted_run_state(state_file: Path, attempted_runs: List[int]) -> None

Updates the `last_attempted_run` value to the maximum run number attempted. This tracks the highest run processed (successfully or not).

**Key Behavior:**
- Always updates to the maximum run number in the list
- Never decreases (monotonically increasing)
- Tracks processing progress regardless of success/failure

**Parameters:**
- `state_file`: Path to the JSON state file
- `attempted_runs`: List of run numbers attempted (order doesn't matter)

**Example:**
```python
# Current state: last_attempted_run = 100
state.update_attempted_run_state(state_file, [101, 105, 103])
# Result: last_attempted_run = 105

# Current state: last_attempted_run = 105
state.update_attempted_run_state(state_file, [98, 99, 100])
# Result: last_attempted_run = 105 (no change, doesn't decrease)

# Current state: last_attempted_run = 105
state.update_attempted_run_state(state_file, [])
# Result: last_attempted_run = 105 (no change, empty list)
```

#### get_incremental_start_run(state_file: Path) -> int

Determines the starting run number for incremental mode. Returns the maximum of `last_contiguous_run` and `last_attempted_run`.

**Key Behavior:**
- Returns 0 if state file doesn't exist
- Uses max of both tracking values to avoid reprocessing
- Ensures incremental mode picks up where last run left off

**Parameters:**
- `state_file`: Path to the JSON state file

**Returns:**
- Starting run number for incremental processing

**Example:**
```python
# State: last_contiguous_run=100, last_attempted_run=150
start = state.get_incremental_start_run(state_file)
print(start)  # Output: 150

# State: last_contiguous_run=200, last_attempted_run=150
start = state.get_incremental_start_run(state_file)
print(start)  # Output: 200

# No state file
start = state.get_incremental_start_run(Path("/nonexistent.json"))
print(start)  # Output: 0
```

#### parse_run_records_from_file(run_records_file: Path) -> List[int]

Parses a text file containing run numbers (one per line). Ignores invalid lines.

**Parameters:**
- `run_records_file`: Path to text file with run numbers

**Returns:**
- List of integer run numbers

**Example:**
```python
# File contents:
# 100
# 200
# invalid
# 300
# 

runs = state.parse_run_records_from_file(Path("/tmp/runs.txt"))
print(runs)  # Output: [100, 200, 300]
```

#### append_to_failure_log(failure_log: Path, failed_runs: List[int]) -> None

Appends failed run numbers to a failure log file. Creates file if it doesn't exist.

**Parameters:**
- `failure_log`: Path to the failure log file
- `failed_runs`: List of run numbers that failed

**Example:**
```python
# Append new failures
failed = [106, 107]
state.append_to_failure_log(Path("/var/archiver/import_failure_log"), failed)

# File contents after append:
# 105
# 106
# 107
```

#### write_failure_log(failure_log: Path, failed_runs: List[int]) -> None

Overwrites failure log file with specified run numbers. Used during recovery operations.

**Parameters:**
- `failure_log`: Path to the failure log file
- `failed_runs`: List of run numbers to write (replaces existing content)

**Example:**
```python
# During state recovery, rebuild failure log
recovered_failures = [105, 110, 115]
state.write_failure_log(Path("/var/archiver/import_failure_log"), recovered_failures)

# File contents after write:
# 105
# 110
# 115
```

### State Tracking Strategy

The archiver uses two tracking mechanisms to handle different scenarios:

#### 1. Contiguous Run Tracking (`last_contiguous_run`)

Tracks the last run in an unbroken sequence of successful runs. This ensures no gaps are left when failures occur.

**Use Case:** Incremental mode that must not skip runs

**Example Scenario:**
```
Runs 100-105 succeed → last_contiguous_run = 105
Run 106 fails, 107-110 succeed → last_contiguous_run = 105 (gap at 106)
Next incremental starts from 105 (will retry 106+)
```

#### 2. Attempted Run Tracking (`last_attempted_run`)

Tracks the highest run number ever attempted (successfully or not). Prevents reprocessing runs beyond failures.

**Use Case:** Avoid redundant work after scattered failures

**Example Scenario:**
```
Process runs 100-110, failures at 103,106 → last_attempted_run = 110
Next incremental starts from 110 (won't reprocess 100-110)
Failure log contains [103, 106] for explicit retry
```

#### 3. Combined Strategy

Both values work together for optimal behavior:

```python
# Scenario: Runs 100-105 succeed, 106 fails, 107-110 succeed
# State: last_contiguous_run=105, last_attempted_run=110

# Incremental mode uses max of both:
start_run = state.get_incremental_start_run(state_file)
# Returns 110 (max of 105 and 110)

# Result: Next run processes from 110 onward (new runs only)
# Failed run 106 remains in failure log for explicit retry via --retry-failed-import
```

### Complete Usage Example

Here's how the state module is used in a typical archival workflow:

```python
from pathlib import Path
from run_record_archiver.persistence import state

# Setup
state_file = Path("/var/archiver/import_state.json")
failure_log = Path("/var/archiver/import_failure_log")

# Read current state
current_state = state.read_state(state_file)
last_contiguous = current_state.get('last_contiguous_run', 0)
last_attempted = current_state.get('last_attempted_run', 0)
print(f"Starting from contiguous={last_contiguous}, attempted={last_attempted}")

# Process a batch of runs
attempted_runs = [101, 102, 103, 104, 105]
successful_runs = [101, 102, 104, 105]  # 103 failed
failed_runs = [103]

# Update state
state.update_contiguous_run_state(state_file, successful_runs)
state.update_attempted_run_state(state_file, attempted_runs)
state.append_to_failure_log(failure_log, failed_runs)

# Check new state
new_state = state.read_state(state_file)
print(f"New state: {new_state}")
# Output: {'last_contiguous_run': 102, 'last_attempted_run': 105}

# Prepare for next incremental run
start_run = state.get_incremental_start_run(state_file)
print(f"Next incremental will start from run {start_run}")
# Output: Next incremental will start from run 105

# Later: Retry failed runs
failed_runs_to_retry = state.parse_run_records_from_file(failure_log)
print(f"Retrying {len(failed_runs_to_retry)} failed runs: {failed_runs_to_retry}")
# Output: Retrying 1 failed runs: [103]

# After successful retry, rebuild failure log (remove 103)
remaining_failures = [r for r in failed_runs_to_retry if r != 103]
state.write_failure_log(failure_log, remaining_failures)
```

## Module: lock.py

The lock module provides file-based locking to prevent concurrent archiver instances from running simultaneously.

### FileLock Class

Context manager that creates an exclusive file lock using `fcntl.flock()`.

#### Constructor

```python
FileLock(lock_file: Path)
```

**Parameters:**
- `lock_file`: Path to the lock file

**Example:**
```python
from pathlib import Path
from run_record_archiver.persistence.lock import FileLock

lock_file = Path("/var/run/archiver.lock")
lock = FileLock(lock_file)
```

#### Context Manager Usage

The FileLock class is designed to be used as a context manager with Python's `with` statement.

**Example:**
```python
from run_record_archiver.persistence.lock import FileLock
from run_record_archiver.exceptions import LockExistsError

lock_file = Path("/var/run/archiver.lock")

try:
    with FileLock(lock_file):
        print("Lock acquired, running archiver...")
        # Do archival work here
        # Lock automatically released when exiting context
except LockExistsError as e:
    print(f"Another instance is running: {e}")
    sys.exit(1)
```

#### Lock Mechanism

**Acquisition (`__enter__`):**
1. Creates parent directories if needed
2. Opens lock file for writing
3. Attempts to acquire exclusive lock with `fcntl.LOCK_EX | fcntl.LOCK_NB`
4. Writes current process PID to lock file
5. Raises `LockExistsError` if lock is already held

**Release (`__exit__`):**
1. Releases lock with `fcntl.LOCK_UN`
2. Closes file handle
3. Automatically called when exiting context (even on exceptions)

#### Methods

##### is_lock_file_valid() -> bool

Checks if the lock file contains the current process's PID. Used for monitoring.

**Returns:**
- `True` if lock file exists and contains current process PID
- `False` otherwise

**Example:**
```python
with FileLock(lock_file) as lock:
    if lock.is_lock_file_valid():
        print("Lock is valid")
    else:
        print("Lock file corrupted or modified")
```

##### get_pid() -> int

Returns the current process ID.

**Returns:**
- Current process PID

**Example:**
```python
lock = FileLock(lock_file)
print(f"Lock will use PID: {lock.get_pid()}")
```

### Error Handling

The FileLock raises `LockExistsError` (from `run_record_archiver.exceptions`) when:
- Another process holds the lock
- File system permissions prevent lock acquisition
- I/O errors occur during lock acquisition

**Example:**
```python
from run_record_archiver.persistence.lock import FileLock
from run_record_archiver.exceptions import LockExistsError

def run_archiver():
    lock_file = Path("/var/run/archiver.lock")
    
    try:
        with FileLock(lock_file):
            # Critical section - only one process can be here
            process_runs()
    except LockExistsError as e:
        logger.error("Cannot acquire lock: %s", e)
        return False
    
    return True
```

### Lock Monitoring Thread

While not implemented in the FileLock class itself, the archiver's main module (`__main__.py`) implements a monitoring thread that periodically validates the lock file:

**Usage Pattern:**
```python
import threading
import time
from run_record_archiver.persistence.lock import FileLock

def monitor_lock_file(lock: FileLock, interval: int = 60):
    """Monitor thread that validates lock every interval seconds."""
    while not shutdown_requested:
        time.sleep(interval)
        if not lock.is_lock_file_valid():
            logger.error("Lock file corrupted or deleted!")
            # Trigger shutdown
            break

# In main:
with FileLock(lock_file) as lock:
    # Start monitoring thread
    monitor_thread = threading.Thread(
        target=monitor_lock_file,
        args=(lock, 60),
        daemon=True
    )
    monitor_thread.start()
    
    # Run archiver
    run_archival_process()
```

### Complete Lock Usage Example

Here's how the lock is used in the archiver's main entry point:

```python
#!/usr/bin/env python3
"""Run Record Archiver main entry point."""

import sys
import logging
from pathlib import Path
from run_record_archiver.persistence.lock import FileLock
from run_record_archiver.exceptions import LockExistsError
from run_record_archiver.orchestrator import Orchestrator

def main():
    # Load configuration
    config = load_config("config.yaml")
    
    # Setup logging
    logger = logging.getLogger(__name__)
    
    # Define lock file path
    lock_file = Path(config['app']['lock_file'])
    
    try:
        # Acquire exclusive lock
        with FileLock(lock_file):
            logger.info("Lock acquired, starting archiver...")
            
            # Run archival process
            orchestrator = Orchestrator(config)
            exit_code = orchestrator.run()
            
            logger.info("Archiver completed successfully")
            return exit_code
            
    except LockExistsError as e:
        logger.error("Another archiver instance is running: %s", e)
        return 1
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        return 2

if __name__ == "__main__":
    sys.exit(main())
```

## Testing Considerations

### State Module Tests

The state module is tested in `tests/test_persistence.py` with coverage for:

- Reading/writing state files
- Handling non-existent and corrupted files
- Parsing run record files with invalid entries
- Updating contiguous run state (gaps, no changes, extensions)
- Updating attempted run state (increases, no decreases, empty lists)
- Getting incremental start run (various state combinations)
- Combined state tracking scenarios (realistic workflows)
- Recovery operations updating state correctly

**Test Example:**
```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from run_record_archiver.persistence import state

class TestState(unittest.TestCase):
    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.state_file = Path(self.tmpdir.name) / "state.json"
    
    def test_contiguous_run_with_gap(self):
        """Test that gaps prevent contiguous advancement."""
        state.write_state(self.state_file, {"last_contiguous_run": 100})
        
        # Process runs with gap
        state.update_contiguous_run_state(self.state_file, [101, 103, 104])
        
        # Should stop at 101 (gap before 103)
        new_state = state.read_state(self.state_file)
        self.assertEqual(new_state["last_contiguous_run"], 101)
```

### Lock Module Tests

The lock module is tested in `tests/test_lock_monitoring.py` with coverage for:

- Basic lock acquisition and release
- Lock contention (multiple processes)
- Lock file validation
- PID tracking
- Error handling (permissions, I/O errors)

**Test Example:**
```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from run_record_archiver.persistence.lock import FileLock
from run_record_archiver.exceptions import LockExistsError

class TestFileLock(unittest.TestCase):
    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.lock_file = Path(self.tmpdir.name) / "test.lock"
    
    def test_lock_prevents_concurrent_access(self):
        """Test that second process cannot acquire lock."""
        with FileLock(self.lock_file):
            # Try to acquire again (simulates second process)
            with self.assertRaises(LockExistsError):
                with FileLock(self.lock_file):
                    pass
```

## Integration Tests

The persistence package is tested in integration scenarios in:

- `tests/test_state_tracking_integration.py`: End-to-end state tracking
- `tests/test_shutdown_state_tracking.py`: State updates during shutdown
- `tests/test_state_recovery.py`: State recovery operations

These tests validate that the persistence layer correctly handles:
- Incremental processing workflows
- Failure and retry scenarios
- State recovery from databases
- Shutdown and cleanup operations

## Configuration

The persistence package uses paths configured in `config.yaml`:

```yaml
app:
  lock_file: "/var/run/run_record_archiver.lock"
  import_state_file: "/var/run_record_archiver/import_state.json"
  import_failure_log: "/var/run_record_archiver/import_failure_log"
  migrate_state_file: "/var/run_record_archiver/migrate_state.json"
  migrate_failure_log: "/var/run_record_archiver/migrate_failure_log"
```

## Best Practices

1. **Always use FileLock as context manager**: Ensures lock release even on exceptions
2. **Update both state values**: Call both `update_contiguous_run_state()` and `update_attempted_run_state()`
3. **Handle state file corruption**: Use `read_state()` which returns empty dict on errors
4. **Sort successful runs before update**: Makes contiguous logic more predictable
5. **Log state changes**: Both functions log updates at INFO level for debugging
6. **Monitor lock file**: Implement monitoring thread for long-running processes
7. **Use write_failure_log() for recovery**: Use `append_to_failure_log()` for normal operation

## Related Documentation

- Main documentation: `/run_record_archiver/readme.md`
- State recovery: `/run_record_archiver/main.md` (--recover-*-state flags)
- Configuration: `/run_record_archiver/config.md`
- Orchestrator: `/run_record_archiver/orchestrator.md`
- Importer: `/run_record_archiver/importer.md`
- Migrator: `/run_record_archiver/migrator.md`
