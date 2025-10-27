# Exit Codes Reference - Run Record Archiver

## Overview

The Run Record Archiver uses standard exit codes to indicate execution status. These codes are essential for:
- Shell script integration
- Monitoring systems
- Automated workflows
- CI/CD pipelines

---

## Exit Code Summary

| Code | Name | Meaning | Action Required |
|------|------|---------|-----------------|
| **0** | Success | All operations completed successfully | None |
| **1** | Known Error | Expected error condition occurred | Review logs, fix issue, retry |
| **2** | Unexpected Error | Unhandled exception or programming error | Review stack trace, report bug |
| **130** | User Interrupt | Graceful shutdown via Ctrl-C (SIGINT) | Resume with --incremental or retry failures |

---

## Exit Code 0: Success

### Meaning
All requested operations completed successfully without errors.

### When This Occurs
- All runs processed successfully
- Status report generated without errors
- State recovery completed successfully
- No failures logged

### Example Output
```
======================================================================
✓ EXECUTION COMPLETED SUCCESSFULLY
======================================================================
```

### Action Required
**None.** Normal successful completion.

### Shell Script Usage
```bash
./run_archiver.sh config.yaml
if [ $? -eq 0 ]; then
    echo "Archiver completed successfully"
    # Continue with next step
fi
```

### Monitoring Integration
```bash
# Nagios/Icinga check
if ./run_archiver.sh config.yaml; then
    echo "OK: Archiver completed successfully"
    exit 0
else
    echo "CRITICAL: Archiver failed with exit code $?"
    exit 2
fi
```

---

## Exit Code 1: Known Error

### Meaning
The archiver encountered a **known, expected error condition** and handled it gracefully. This includes:
- Configuration errors
- Database connection failures
- Lock file conflicts
- Partial processing failures
- Validation errors

### Common Causes

#### 1. Configuration Errors
```
ConfigurationError: work_dir is required
```
**Fix:** Correct configuration file

#### 2. Lock File Exists
```
LockExistsError: Another process may be running
```
**Fix:** Wait for other process or remove stale lock

#### 3. Database Connection Failures
```
ArtdaqDBError: Failed to connect to database
UconDBError: Failed to initialize UConDB client
```
**Fix:** Verify network connectivity and credentials

#### 4. File System Errors
```
ArchiverError: Cannot read run records directory
```
**Fix:** Check permissions and paths

#### 5. Partial Processing Failures
```
Import Stage: Some runs failed (see failure log)
```
**Fix:** Review failure log, retry with --retry-failed-import

### Example Output
```
======================================================================
ERROR SUMMARY
======================================================================
Failed Stage: Import
Error Type: ArtdaqDBError
Error Message: Failed to connect to database
======================================================================
```

### Action Required

**Step 1: Check logs for specific error**
```bash
tail -100 /var/lib/run_record_archiver/archiver.log | grep -i error
```

**Step 2: Review failure logs**
```bash
cat /var/lib/run_record_archiver/import_failures.log
cat /var/lib/run_record_archiver/migrate_failures.log
```

**Step 3: Fix underlying issue**
- Configuration: Correct config.yaml
- Connectivity: Fix network or database issues
- Permissions: Adjust file/directory permissions
- Lock: Remove stale lock file

**Step 4: Retry**
```bash
# Retry specific failures
./run_archiver.sh config.yaml --retry-failed-import
./run_archiver.sh config.yaml --retry-failed-migrate

# Or resume incremental processing
./run_archiver.sh config.yaml --incremental
```

### Shell Script Handling
```bash
#!/bin/bash

./run_archiver.sh config.yaml
EXIT_CODE=$?

if [ $EXIT_CODE -eq 1 ]; then
    echo "Known error occurred, checking logs..."
    
    # Check for specific errors
    if grep -q "LockExistsError" /var/lib/run_record_archiver/archiver.log; then
        echo "Another instance running, will retry later"
        exit 0  # Not a critical error
    fi
    
    # Check failure counts
    IMPORT_FAILURES=$(wc -l < /var/lib/run_record_archiver/import_failures.log)
    if [ $IMPORT_FAILURES -gt 0 ]; then
        echo "Warning: $IMPORT_FAILURES import failures"
        # Trigger alert
    fi
    
    exit 1
fi
```

### Monitoring Integration
```bash
# Systemd OnFailure handler
[Unit]
OnFailure=archiver-failure-handler@%n.service

# Handler service
[Service]
Type=oneshot
ExecStart=/usr/local/bin/archiver-alert.sh %i
```

---

## Exit Code 2: Unexpected Error

### Meaning
An **unhandled exception** occurred - something the developers didn't anticipate. This typically indicates:
- Programming bugs
- Environment issues
- Corrupt data
- System resource exhaustion
- Library incompatibilities

### Common Causes

#### 1. Missing Dependencies
```
ModuleNotFoundError: No module named 'yaml'
```
**Fix:** Install missing Python packages

#### 2. Library Version Mismatch
```
AttributeError: module 'conftoolp' has no attribute 'find_configurations'
```
**Fix:** Verify bundled libraries are correct version

#### 3. System Resource Exhaustion
```
MemoryError: Unable to allocate array
OSError: [Errno 24] Too many open files
```
**Fix:** Increase system limits or reduce parallel_workers

#### 4. File System Corruption
```
OSError: [Errno 5] Input/output error
```
**Fix:** Check filesystem integrity

#### 5. Programming Bugs
```
TypeError: unsupported operand type(s)
KeyError: 'expected_key'
```
**Fix:** Report to developers with stack trace

### Example Output
```
======================================================================
UNEXPECTED ERROR SUMMARY
======================================================================
Failed Stage: Import
Error Type: TypeError
Error Message: unsupported operand type(s) for +: 'int' and 'str'
======================================================================
Full traceback:
  File "importer.py", line 123, in process_run
    total = run_number + config_name
TypeError: unsupported operand type(s) for +: 'int' and 'str'
```

### Action Required

**Step 1: Review full stack trace**
```bash
grep -A 50 "UNEXPECTED ERROR SUMMARY" /var/lib/run_record_archiver/archiver.log
```

**Step 2: Enable debug logging**
```bash
./run_archiver.sh config.yaml -v
```

**Step 3: Check environment**
```bash
# Verify Python version
python3 --version

# Verify dependencies
pip list | grep -E "yaml|requests|ucondb"

# Check system resources
df -h
free -h
ulimit -a
```

**Step 4: Report bug if reproducible**
Include:
- Full error message and stack trace
- Configuration file (sanitized)
- Steps to reproduce
- Environment details (OS, Python version)

### Shell Script Handling
```bash
#!/bin/bash

./run_archiver.sh config.yaml
EXIT_CODE=$?

if [ $EXIT_CODE -eq 2 ]; then
    echo "CRITICAL: Unexpected error occurred"
    
    # Capture error details
    ERROR_LOG="/var/lib/run_record_archiver/archiver.log"
    REPORT_FILE="/tmp/archiver-error-$(date +%Y%m%d-%H%M%S).txt"
    
    # Extract error info
    {
        echo "Timestamp: $(date)"
        echo "Exit Code: $EXIT_CODE"
        echo "---"
        grep -A 50 "UNEXPECTED ERROR" "$ERROR_LOG"
    } > "$REPORT_FILE"
    
    # Send alert
    mail -s "Archiver Unexpected Error" admin@example.com < "$REPORT_FILE"
    
    exit 2
fi
```

### Monitoring Integration
```python
# Python monitoring script
import subprocess
import sys

result = subprocess.run(
    ['./run_archiver.sh', 'config.yaml'],
    capture_output=True
)

if result.returncode == 2:
    # Critical alert
    send_pagerduty_alert(
        severity='critical',
        summary='Archiver unexpected error',
        details=result.stderr.decode()
    )
    sys.exit(2)
```

---

## Exit Code 130: User Interrupt

### Meaning
The archiver was **intentionally interrupted** by the user sending SIGINT (Ctrl-C). The archiver performed a **graceful shutdown**:
- Current run completed or failed
- State saved to disk
- Lock file removed
- Clean exit

### When This Occurs
- User pressed Ctrl-C once (graceful shutdown)
- SIGINT signal sent to process
- Systemd service stopped gracefully

### Shutdown Behavior

**Single Ctrl-C (Graceful):**
```
======================================================================
GRACEFUL SHUTDOWN REQUESTED (Ctrl-C)
Current run will finish processing...
Press Ctrl-C two more times within 2 seconds for immediate shutdown
======================================================================
✓ GRACEFUL SHUTDOWN COMPLETED
Reason: User interrupt
======================================================================
```

**Triple Ctrl-C (Immediate):**
```
======================================================================
IMMEDIATE SHUTDOWN REQUESTED (3x Ctrl-C)
======================================================================
```
Exit code: Still 130, but no state saved

### Example Output
```
======================================================================
✓ GRACEFUL SHUTDOWN COMPLETED
Reason: User interrupt
======================================================================
```

### Action Required

**Resume Processing:**
```bash
# Resume from where you left off
./run_archiver.sh config.yaml --incremental

# Or retry any failures
./run_archiver.sh config.yaml --retry-failed-import
./run_archiver.sh config.yaml --retry-failed-migrate
```

**Verify State:**
```bash
# Check last processed run
cat /var/lib/run_record_archiver/importer_state.json
cat /var/lib/run_record_archiver/migrator_state.json
```

### Shell Script Handling
```bash
#!/bin/bash

# Set up trap to handle Ctrl-C
trap 'echo "Archiver interrupted, exiting"; exit 130' INT

./run_archiver.sh config.yaml
EXIT_CODE=$?

if [ $EXIT_CODE -eq 130 ]; then
    echo "Archiver was interrupted by user"
    echo "State saved, resume with: ./run_archiver.sh config.yaml --incremental"
    # Not an error - clean exit
    exit 0
fi
```

### Systemd Integration
```ini
[Service]
# Graceful shutdown on stop
KillMode=mixed
KillSignal=SIGINT
TimeoutStopSec=300

# Restart on failure, but not on user interrupt
Restart=on-failure
RestartPreventExitStatus=130
```

---

## Exit Code Usage in Scripts

### Basic Error Handling
```bash
#!/bin/bash

./run_archiver.sh config.yaml

case $? in
    0)
        echo "Success"
        ;;
    1)
        echo "Known error - check logs"
        exit 1
        ;;
    2)
        echo "Unexpected error - investigate"
        exit 2
        ;;
    130)
        echo "User interrupted - will resume later"
        exit 0
        ;;
    *)
        echo "Unknown exit code: $?"
        exit 3
        ;;
esac
```

### Automated Retry Logic
```bash
#!/bin/bash

MAX_RETRIES=3
RETRY_DELAY=300  # 5 minutes

for i in $(seq 1 $MAX_RETRIES); do
    ./run_archiver.sh config.yaml
    EXIT_CODE=$?
    
    case $EXIT_CODE in
        0)
            echo "Success on attempt $i"
            exit 0
            ;;
        1)
            echo "Known error on attempt $i, retrying in ${RETRY_DELAY}s"
            sleep $RETRY_DELAY
            ;;
        2)
            echo "Unexpected error - aborting retries"
            exit 2
            ;;
        130)
            echo "User interrupted - stopping"
            exit 130
            ;;
    esac
done

echo "Failed after $MAX_RETRIES attempts"
exit 1
```

### Monitoring Check Script
```bash
#!/bin/bash
# Nagios/Icinga plugin

OUTPUT=""
PERFDATA=""

./run_archiver.sh config.yaml 2>&1 | tee /tmp/archiver.out
EXIT_CODE=$?

# Count failures
IMPORT_FAIL=$(wc -l < /var/lib/run_record_archiver/import_failures.log 2>/dev/null || echo 0)
MIGRATE_FAIL=$(wc -l < /var/lib/run_record_archiver/migrate_failures.log 2>/dev/null || echo 0)

PERFDATA="import_failures=$IMPORT_FAIL migrate_failures=$MIGRATE_FAIL"

case $EXIT_CODE in
    0)
        if [ $IMPORT_FAIL -eq 0 ] && [ $MIGRATE_FAIL -eq 0 ]; then
            echo "OK: Archiver completed successfully | $PERFDATA"
            exit 0
        else
            echo "WARNING: Archiver succeeded but has failures | $PERFDATA"
            exit 1
        fi
        ;;
    1)
        echo "WARNING: Known error occurred | $PERFDATA"
        exit 1
        ;;
    2)
        echo "CRITICAL: Unexpected error occurred | $PERFDATA"
        exit 2
        ;;
    130)
        echo "OK: User interrupted (graceful) | $PERFDATA"
        exit 0
        ;;
    *)
        echo "UNKNOWN: Unexpected exit code $EXIT_CODE | $PERFDATA"
        exit 3
        ;;
esac
```

---

## Quick Reference Table

| Exit Code | Severity | Retry Safe? | Alert Level | Monitoring Status |
|-----------|----------|-------------|-------------|-------------------|
| 0 | Success | N/A | None | OK |
| 1 | Warning | Yes | Warning | WARNING |
| 2 | Critical | No | Critical | CRITICAL |
| 130 | Info | N/A | None | OK |

---

## Related Documentation

- [Troubleshooting Guide](TROUBLESHOOTING_GUIDE.md) - Solutions for exit code 1 errors
- [Operations Manual](OPERATIONS_MANUAL.md) - Monitoring and alerting setup
- [Command-Line Reference](../run_record_archiver/main.md) - All CLI options
- [Deployment Guide](DEPLOYMENT_GUIDE.md) - Systemd integration

**Last Updated:** 2025-10-24
