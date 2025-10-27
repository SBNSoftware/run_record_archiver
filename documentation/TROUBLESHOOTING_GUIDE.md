# Troubleshooting Guide - Run Record Archiver

## Table of Contents

- [Overview](#overview)
- [Quick Diagnosis](#quick-diagnosis)
- [Error Categories](#error-categories)
  - [Configuration Errors](#configuration-errors)
  - [Database Connection Errors](#database-connection-errors)
  - [Network Errors](#network-errors)
  - [File System Errors](#file-system-errors)
  - [Lock File Conflicts](#lock-file-conflicts)
  - [Memory and Performance Issues](#memory-and-performance-issues)
- [Exit Code Reference](#exit-code-reference)
- [Common Error Messages](#common-error-messages)
- [Debug Logging](#debug-logging)
- [State File Issues](#state-file-issues)
- [Known Issues and Workarounds](#known-issues-and-workarounds)
- [Getting Help](#getting-help)

---

## Overview

This guide provides solutions to common issues encountered when deploying and operating the Run Record Archiver. Each section includes:

- **Symptom**: What you'll see in logs or output
- **Cause**: Why the error occurs
- **Solution**: Step-by-step fix
- **Prevention**: How to avoid the issue

For error messages not covered here, see [Exit Code Reference](#exit-code-reference) or enable [Debug Logging](#debug-logging) for detailed diagnostics.

---

## Quick Diagnosis

### Step 1: Check Exit Code

```bash
./run_archiver.sh config.yaml
echo "Exit code: $?"
```

- **0**: Success - no action needed
- **1**: Known error - check logs for specific message
- **2**: Unexpected error - review full stack trace
- **130**: User interrupt (Ctrl-C) - graceful shutdown

### Step 2: Check Recent Log Entries

```bash
# View last 50 log lines
tail -50 /var/lib/run_record_archiver/archiver.log

# Search for errors
grep -i "error\|critical\|exception" /var/lib/run_record_archiver/archiver.log | tail -20
```

### Step 3: Identify Stage

Look for stage indicators in log messages:

- `[Import]` - Import stage (filesystem → artdaqDB)
- `[Migration]` - Migration stage (artdaqDB → UconDB)
- `[Recovery-Import]` - Import state recovery
- `[Recovery-Migration]` - Migration state recovery
- `[Report]` - Status reporting
- `[Validation]` - Blob validation

### Step 4: Check Failure Logs

```bash
# Import failures
cat /var/lib/run_record_archiver/import_failures.log

# Migration failures
cat /var/lib/run_record_archiver/migrate_failures.log
```

---

## Error Categories

### Configuration Errors

#### Error: `ConfigurationError: Configuration validation failed`

**Symptom:**
```
ConfigurationError: Configuration validation failed: work_dir is required
```

**Cause:** Missing or invalid required configuration parameters.

**Solution:**

```bash
# 1. Validate YAML syntax
python3 -c "import yaml; yaml.safe_load(open('config.yaml'))"

# 2. Check for required parameters
grep -E "work_dir|database_uri|server_url" config.yaml

# 3. Verify environment variables
echo "WORK_DIR: $WORK_DIR"
echo "ARTDAQDB_URL: $ARTDAQDB_URL"
echo "UCONDB_URL: $UCONDB_URL"

# 4. Test configuration loading
python3 << 'EOF'
from run_record_archiver.config import Config
try:
    config = Config.from_file('config.yaml')
    print("✓ Configuration loaded successfully")
except Exception as e:
    print(f"✗ Configuration error: {e}")
EOF
```

**Prevention:** Use `config.yaml.template` as a starting point; validate configuration after changes.

---

#### Error: `FclPreperationError: FCL confdir '/path/to/conf' is not a directory`

**Symptom:**
```
[Import] [Run 12345] FclPreperationError: FCL confdir '${HOME}/artdaq/conf' is not a directory
```

**Cause:** Invalid `artdaq_db.fcl_conf_dir` path in configuration.

**Solution:**

```bash
# 1. Check configured path
grep fcl_conf_dir config.yaml

# 2. Verify directory exists
ls -la ${HOME}/artdaq/conf

# 3. Check for schema.fcl
ls -la ${HOME}/artdaq/conf/schema.fcl

# 4. Fix configuration
vim config.yaml
# Update artdaq_db.fcl_conf_dir to correct path

# 5. Test
./run_archiver.sh config.yaml --report-status
```

**Prevention:** Verify all paths during initial deployment; use absolute paths.

---

#### Error: `FclPreperationError: Schema not found at /path/to/schema.fcl`

**Symptom:**
```
FclPreperationError: Schema not found at ${HOME}/artdaq/conf/schema.fcl
```

**Cause:** Missing `schema.fcl` file required for artdaqDB operations.

**Solution:**

```bash
# 1. Locate schema.fcl in bundled lib directory
find ${HOME}/run_record_archiver/lib -name "schema.fcl"

# 2. Copy to configured location
cp ${HOME}/run_record_archiver/lib/schema.fcl ${HOME}/artdaq/conf/

# OR update configuration to point to bundled schema
vim config.yaml
# Set: fcl_conf_dir: "${HOME}/run_record_archiver/lib"
```

**Prevention:** Use bundled schema location in configuration.

---

### Database Connection Errors

#### Error: `ModuleNotFoundError: No module named 'conftoolp'`

**Symptom:**
```
ModuleNotFoundError: No module named 'conftoolp'
ImportError: Failed to import 'conftoolp'. Ensure artdaq_database env is set up.
```

**Cause:** Python cannot find the `conftoolp` module in the bundled `lib/` directory.

**Solution:**

```bash
# 1. Verify lib directory exists
ls -la ${HOME}/run_record_archiver/lib/conftoolp.py
ls -la ${HOME}/run_record_archiver/lib/_conftoolp.so

# 2. Check PYTHONPATH (if running manually)
echo $PYTHONPATH
# Should contain: ${HOME}/run_record_archiver/lib

# 3. Use run_archiver.sh (sets environment automatically)
./run_archiver.sh config.yaml --help

# 4. If running manually, set environment
export PYTHONPATH="${HOME}/run_record_archiver/lib:${PYTHONPATH}"
export LD_LIBRARY_PATH="${HOME}/run_record_archiver/lib:${LD_LIBRARY_PATH}"

# 5. Test import
python3 -c "import conftoolp; print('✓ conftoolp imported successfully')"
```

**Prevention:** Always use `run_archiver.sh` for execution; it handles environment setup.

---

#### Error: `ImportError: libartdaq-database_ConfigurationDB.so: cannot open shared object file`

**Symptom:**
```
ImportError: libartdaq-database_ConfigurationDB.so: cannot open shared object file: No such file or directory
```

**Cause:** Shared library loader cannot find bundled `.so` files.

**Solution:**

```bash
# 1. Verify shared libraries exist
ls -la ${HOME}/run_record_archiver/lib/*.so

# 2. Check LD_LIBRARY_PATH
echo $LD_LIBRARY_PATH
# Should contain: ${HOME}/run_record_archiver/lib

# 3. Set explicitly
export LD_LIBRARY_PATH="${HOME}/run_record_archiver/lib:${LD_LIBRARY_PATH}"

# 4. Verify library loading
ldd ${HOME}/run_record_archiver/lib/_conftoolp.so

# 5. Use run_archiver.sh (recommended)
./run_archiver.sh config.yaml
```

**Prevention:** Use `run_archiver.sh`; avoid manual `python -m run_record_archiver` execution.

---

#### Error: `ArtdaqDBError: Failed to get configurations`

**Symptom:**
```
[Import] ArtdaqDBError: Failed to get configurations: {'success': False, 'result': 'Connection refused'}
```

**Cause:** Cannot connect to MongoDB server or access FilesystemDB.

**Solution for MongoDB:**

```bash
# 1. Test MongoDB connectivity
mongo --host mongodb-host --port 27017 --eval "db.version()"

# 2. Check database URI format
grep database_uri config.yaml
# Should be: mongodb://user:pass@host:port/database_archive

# 3. Verify credentials
mongo --host mongodb-host --port 27017 -u archiver -p

# 4. Check firewall rules
telnet mongodb-host 27017

# 5. Test connection from Python
python3 << 'EOF'
from pymongo import MongoClient
client = MongoClient("mongodb://host:27017")
print(client.server_info())
EOF
```

**Solution for FilesystemDB:**

```bash
# 1. Verify path exists and is accessible
ls -la /path/to/artdaqdb_archive

# 2. Check permissions
# Must be readable/writable by archiver user
sudo chown -R archiver:archiver /path/to/artdaqdb_archive
sudo chmod -R 755 /path/to/artdaqdb_archive

# 3. Check database URI format
grep database_uri config.yaml
# Should be: filesystemdb:///absolute/path/to/artdaqdb_archive
# Note: Three slashes (///) for absolute paths

# 4. Test manual access
cd /path/to/artdaqdb_archive
ls -la
```

**Prevention:** Use `--report-status` to test connectivity before full runs.

---

#### Error: `ArtdaqDBError: Configuration X is already archived`

**Symptom:**
```
[Import] [Run 12345] ArtdaqDBError: Configuration 12345/BootDAQ is already archived.
```

**Cause:** Attempting to insert run that already exists in artdaqDB without update mode.

**Solution:**

```bash
# This is usually a warning, not an error (run skipped)
# If this happens frequently:

# 1. Use incremental mode
./run_archiver.sh config.yaml --incremental

# 2. Recover state tracking
./run_archiver.sh config.yaml --recover-import-state

# 3. Check for concurrent execution
ps aux | grep run_archiver

# 4. Verify lock file not stale
ls -la /var/lib/run_record_archiver/.archiver.lock
```

**Prevention:** Use incremental mode for scheduled runs; avoid concurrent execution.

---

#### Error: `UconDBError: Failed to initialize UConDB client`

**Symptom:**
```
[Migration] UconDBError: Failed to initialize UConDB client: Connection refused
```

**Cause:** Cannot connect to UconDB server.

**Solution:**

```bash
# 1. Test network connectivity
ping -c 3 ucondb.example.com

# 2. Test HTTPS access
curl -k https://ucondb.example.com:9443/instance/app

# 3. Verify server URL format
grep server_url config.yaml
# Must end with /app: https://host:port/instance/app

# 4. Test credentials
curl -k -u username:password https://ucondb.example.com:9443/instance/app/folders

# 5. Check firewall rules
telnet ucondb.example.com 9443

# 6. Verify SSL certificate (if not using -k)
openssl s_client -connect ucondb.example.com:9443
```

**Prevention:** Test UconDB connectivity during deployment; use `--report-status`.

---

#### Error: `UconDBError: Failed to upload blob for run X`

**Symptom:**
```
[Migration] [Run 12345] UconDBError: Failed to upload blob for run 12345: 403 Forbidden
```

**Cause:** Insufficient permissions or invalid credentials for UconDB write operations.

**Solution:**

```bash
# 1. Verify credentials
echo "User: $UCONDB_USER"
echo "Password: (check archiver.env)"

# 2. Test write permissions
curl -k -u $UCONDB_USER:$UCONDB_PASSWORD \
  -X POST \
  https://ucondb.example.com:9443/instance/app/folders/test/versions

# 3. Check UconDB user permissions
# Contact UconDB administrator to verify write access

# 4. Verify folder exists
./run_archiver.sh config.yaml --report-status
# Check UconDB section for folder accessibility
```

**Prevention:** Verify write permissions during deployment; use service account with minimal required permissions.

---

### Network Errors

#### Error: `requests.exceptions.ConnectionError: Connection refused`

**Symptom:**
```
requests.exceptions.ConnectionError: HTTPSConnectionPool(host='ucondb.example.com', port=9443): 
Max retries exceeded with url: /instance/app/folders
```

**Cause:** Network connectivity issues to UconDB server.

**Solution:**

```bash
# 1. Test basic connectivity
ping ucondb.example.com

# 2. Test port access
nc -zv ucondb.example.com 9443

# 3. Check routing
traceroute ucondb.example.com

# 4. Verify DNS resolution
nslookup ucondb.example.com

# 5. Check local firewall
sudo firewall-cmd --list-all
# OR
sudo iptables -L

# 6. Test from same host with curl
curl -v https://ucondb.example.com:9443/instance/app
```

**Prevention:** Configure monitoring for UconDB server availability; set up alerts.

---

#### Error: `requests.exceptions.Timeout: Read timed out`

**Symptom:**
```
[Migration] [Run 12345] requests.exceptions.Timeout: Read timed out (read timeout=30)
```

**Cause:** UconDB server slow to respond or network latency.

**Solution:**

```bash
# 1. Increase timeout in configuration
vim config.yaml
# Update: ucon_db.timeout_seconds: 60

# 2. Check server load
# Contact UconDB administrator

# 3. Test upload speed
time curl -k -u $UCONDB_USER:$UCONDB_PASSWORD \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"test":"data"}' \
  https://ucondb.example.com:9443/instance/app/folders/test/versions

# 4. Check network latency
ping -c 10 ucondb.example.com
```

**Prevention:** Set appropriate timeout values based on network characteristics; monitor server performance.

---

#### Error: `VerificationError: MD5 mismatch between generated and downloaded blobs`

**Symptom:**
```
[Migration] [Run 12345] VerificationError: MD5 mismatch between generated and downloaded blobs
Context: {'generated_md5': 'abc123...', 'downloaded_md5': 'def456...'}
```

**Cause:** Data corruption during upload or server-side modification.

**Solution:**

```bash
# 1. Retry upload (automatic with run_process_retries)
./run_archiver.sh config.yaml --retry-failed-migrate

# 2. If persistent, check network integrity
# Run network diagnostics

# 3. Download and compare manually
# (Requires manual inspection of blob content)

# 4. Check server logs for errors
# Contact UconDB administrator

# 5. Verify disk integrity on both sides
# Check for filesystem corruption
```

**Prevention:** Enable `--validate` flag for all migrations; monitor for patterns.

---

### File System Errors

#### Error: `ArchiverError: Cannot read run records directory`

**Symptom:**
```
[Import] ArchiverError: Cannot read run records directory: [Errno 13] Permission denied
Context: {'directory': '/daq/run_records'}
```

**Cause:** Insufficient permissions to read source run records.

**Solution:**

```bash
# 1. Check directory permissions
ls -la /daq/run_records

# 2. Verify archiver user can read
sudo -u archiver ls /daq/run_records

# 3. Fix permissions (if authorized)
sudo chmod 755 /daq/run_records
sudo chmod -R 644 /daq/run_records/*

# 4. Add archiver user to appropriate group
sudo usermod -aG daq_users archiver

# 5. Test access
./run_archiver.sh config.yaml --report-status
```

**Prevention:** Ensure proper group membership during deployment; document required permissions.

---

#### Error: `ArchiverError: Run directory not found`

**Symptom:**
```
[Import] [Run 12345] ArchiverError: Run directory not found
Context: {'directory': '/daq/run_records/12345'}
```

**Cause:** Run directory disappeared between scan and processing (race condition).

**Solution:**

```bash
# 1. Verify directory actually exists
ls -la /daq/run_records/12345

# 2. Check for filesystem issues
df -h /daq/run_records
# Verify mount point is healthy

# 3. If NFS mount, check mount status
mount | grep run_records
df -h | grep run_records

# 4. Retry run
./run_archiver.sh config.yaml --retry-failed-import

# 5. If persistent, investigate filesystem stability
# Check system logs: dmesg, /var/log/messages
```

**Prevention:** Ensure stable filesystem; avoid processing runs while they're being written.

---

#### Error: `PermissionError: [Errno 13] Permission denied: '/var/lib/run_record_archiver/archiver.log'`

**Symptom:**
```
PermissionError: [Errno 13] Permission denied: '/var/lib/run_record_archiver/archiver.log'
```

**Cause:** Work directory or log files not writable by archiver process.

**Solution:**

```bash
# 1. Check ownership
ls -la /var/lib/run_record_archiver

# 2. Fix ownership
sudo chown -R archiver:archiver /var/lib/run_record_archiver

# 3. Fix permissions
sudo chmod 755 /var/lib/run_record_archiver
sudo chmod 644 /var/lib/run_record_archiver/*.log
sudo chmod 644 /var/lib/run_record_archiver/*.json

# 4. Verify user can write
sudo -u archiver touch /var/lib/run_record_archiver/test.txt
sudo -u archiver rm /var/lib/run_record_archiver/test.txt

# 5. Test archiver
./run_archiver.sh config.yaml --report-status
```

**Prevention:** Set correct permissions during deployment; use systemd service with proper User= directive.

---

#### Error: `OSError: [Errno 28] No space left on device`

**Symptom:**
```
OSError: [Errno 28] No space left on device
```

**Cause:** Insufficient disk space for logs, temporary files, or state files.

**Solution:**

```bash
# 1. Check disk usage
df -h /var/lib/run_record_archiver
df -h /tmp

# 2. Check log file sizes
ls -lh /var/lib/run_record_archiver/*.log

# 3. Clean up old log backups
ls -lh /var/lib/run_record_archiver/*.log.*
# Archiver keeps 5 backups by default

# 4. Rotate logs manually if needed
mv /var/lib/run_record_archiver/archiver.log \
   /var/lib/run_record_archiver/archiver.log.old
rm /var/lib/run_record_archiver/archiver.log.*

# 5. Adjust log rotation in config
vim config.yaml
# See constants: LOG_FILE_MAX_BYTES, LOG_FILE_BACKUP_COUNT
```

**Prevention:** Monitor disk space; set up log rotation; configure alerts for low disk space.

---

### Lock File Conflicts

#### Error: `LockExistsError: Another process may be running`

**Symptom:**
```
LockExistsError: Another process may be running. Lock file '/var/lib/run_record_archiver/.archiver.lock' is held.
```

**Cause:** Another archiver instance is running, or stale lock file from crash.

**Solution:**

```bash
# 1. Check if archiver is actually running
ps aux | grep run_record_archiver
# OR
pgrep -f run_record_archiver

# 2a. If running, wait for completion
# OR use graceful shutdown:
pkill -SIGINT -f run_record_archiver

# 2b. If NOT running, remove stale lock
rm /var/lib/run_record_archiver/.archiver.lock

# 3. Verify lock file removed
ls -la /var/lib/run_record_archiver/.archiver.lock

# 4. Retry archiver
./run_archiver.sh config.yaml
```

**Prevention:** Ensure proper shutdown; use systemd for process management; monitor for crashes.

---

#### Warning: `LOCK FILE REMOVED - INITIATING GRACEFUL SHUTDOWN`

**Symptom:**
```
======================================================================
LOCK FILE REMOVED - INITIATING GRACEFUL SHUTDOWN
Lock file: /var/lib/run_record_archiver/.archiver.lock
Process will finish current run and then exit
======================================================================
```

**Cause:** External process or admin manually removed lock file during execution.

**Solution:**

This is an informational message, not an error. The archiver will:
1. Finish processing the current run
2. Save state
3. Exit gracefully with exit code 1

**To prevent:**
```bash
# Never manually remove lock file while archiver is running
# Use graceful shutdown instead:
pkill -SIGINT -f run_record_archiver

# Or for immediate shutdown (3x Ctrl-C within 2 seconds):
pkill -SIGINT -f run_record_archiver
sleep 0.5
pkill -SIGINT -f run_record_archiver
sleep 0.5
pkill -SIGINT -f run_record_archiver
```

**Prevention:** Document shutdown procedures; avoid manual lock file manipulation.

---

### Memory and Performance Issues

#### Symptom: Archiver runs slowly

**Observations:**
- Low CPU utilization
- Slow database operations
- High network latency

**Solution:**

```bash
# 1. Increase parallel workers (if CPU allows)
vim config.yaml
# Update: app.parallel_workers: 8

# 2. Use CLI tools mode for bulk operations
vim config.yaml
# Update: artdaq_db.use_tools: true

# 3. Check database performance
# MongoDB: Check indexes, query execution time
# FilesystemDB: Check disk I/O (iostat)

# 4. Profile network latency
ping -c 100 ucondb.example.com | tail -1

# 5. Reduce batch size if memory constrained
vim config.yaml
# Update: app.batch_size: 3
```

**Prevention:** Tune performance parameters based on system resources; monitor metrics.

---

#### Symptom: High memory usage

**Observations:**
```bash
# Check memory usage
ps aux | grep run_archiver
top -p $(pgrep -f run_archiver)
```

**Solution:**

```bash
# 1. Reduce parallel workers
vim config.yaml
# Update: app.parallel_workers: 2

# 2. Reduce batch size
vim config.yaml
# Update: app.batch_size: 3

# 3. Monitor memory during execution
watch -n 5 'ps aux | grep run_archiver'

# 4. Set memory limits (systemd)
# See DEPLOYMENT_GUIDE.md for systemd MemoryMax setting
```

**Prevention:** Right-size parallel_workers and batch_size for available memory.

---

## Exit Code Reference

### Exit Code 0: Success
All operations completed successfully.

**No action needed.**

---

### Exit Code 1: Known Error
Archiver encountered a known error condition (ArchiverError, LockExistsError).

**Actions:**

1. **Check logs** for specific error message:
   ```bash
   tail -100 /var/lib/run_record_archiver/archiver.log | grep -i "error\|critical"
   ```

2. **Check failure logs**:
   ```bash
   cat /var/lib/run_record_archiver/import_failures.log
   cat /var/lib/run_record_archiver/migrate_failures.log
   ```

3. **Retry failures** after fixing underlying issue:
   ```bash
   ./run_archiver.sh config.yaml --retry-failed-import
   ./run_archiver.sh config.yaml --retry-failed-migrate
   ```

4. **Review error-specific solutions** in this guide.

---

### Exit Code 2: Unexpected Error
Unhandled exception occurred (programming error or unexpected condition).

**Actions:**

1. **Review full stack trace** in logs:
   ```bash
   grep -A 50 "UNEXPECTED ERROR SUMMARY" /var/lib/run_record_archiver/archiver.log
   ```

2. **Check for environment issues**:
   - Missing dependencies
   - Library version mismatches
   - Filesystem corruption
   - System resource exhaustion

3. **Enable debug logging**:
   ```bash
   ./run_archiver.sh config.yaml -v
   ```

4. **Report bug** if reproducible with stack trace and steps to reproduce.

---

### Exit Code 130: User Interrupt
Graceful shutdown via Ctrl-C (SIGINT).

**This is normal** when you intentionally stop the archiver.

**Resume operations:**
```bash
# Resume from where you left off (incremental mode)
./run_archiver.sh config.yaml --incremental

# Or retry any failures
./run_archiver.sh config.yaml --retry-failed-import
./run_archiver.sh config.yaml --retry-failed-migrate
```

---

## Common Error Messages

### "Failed to parse run records file"

**Full Message:**
```
Failed to parse run records file /var/lib/run_record_archiver/import_failures.log: invalid literal
```

**Cause:** Corrupted failure log file.

**Solution:**
```bash
# Backup and clear
mv /var/lib/run_record_archiver/import_failures.log \
   /var/lib/run_record_archiver/import_failures.log.corrupted
touch /var/lib/run_record_archiver/import_failures.log
```

---

### "No converter found for configured file"

**Full Message:**
```
No converter found for configured file: custom_config.txt
```

**Cause:** File listed in `fhiclize_generate` but no converter implemented.

**Solution:**
```bash
# Option 1: Remove from configuration
vim config.yaml
# Remove 'custom_config.txt' from fhiclize_generate list

# Option 2: Implement converter
# See EXTENSION_GUIDE.md for adding converters
```

---

### "Configuration X not found for update"

**Full Message:**
```
[Import] [Run 12345] ArtdaqDBError: Configuration 12345/BootDAQ not found for update
```

**Cause:** Attempting update on non-existent run (logic error).

**Solution:**
```bash
# This indicates a bug - report to developers
# Workaround: Recover import state
./run_archiver.sh config.yaml --recover-import-state
```

---

## Debug Logging

### Enable Debug Logging

**Method 1: Command-line flag (temporary)**
```bash
./run_archiver.sh config.yaml --verbose
# OR
./run_archiver.sh config.yaml -v
```

**Method 2: Configuration file (persistent)**
```yaml
app:
    log_level: "DEBUG"
```

### Debug Log Analysis

**Find errors:**
```bash
grep -i "error\|exception" /var/lib/run_record_archiver/archiver.log
```

**Trace specific run:**
```bash
grep "Run 12345" /var/lib/run_record_archiver/archiver.log
```

**Show only critical issues:**
```bash
grep -E "CRITICAL|ERROR" /var/lib/run_record_archiver/archiver.log
```

**Follow logs in real-time:**
```bash
tail -f /var/lib/run_record_archiver/archiver.log
```

**Extract exception details:**
```bash
grep -A 20 "Exception raised" /var/lib/run_record_archiver/archiver.log
```

### Interpreting Debug Output

Debug logging shows:
- Configuration expansion (environment variables)
- Database queries and responses
- Network requests and responses
- File operations
- State transitions
- Exception context

---

## State File Issues

### Symptom: Runs processed repeatedly

**Cause:** State file corruption or incremental mode not working.

**Solution:**
```bash
# 1. Check state file content
cat /var/lib/run_record_archiver/importer_state.json
cat /var/lib/run_record_archiver/migrator_state.json

# 2. Recover state from actual data sources
./run_archiver.sh config.yaml --recover-import-state
./run_archiver.sh config.yaml --recover-migrate-state

# 3. Verify state after recovery
cat /var/lib/run_record_archiver/importer_state.json
```

---

### Symptom: Gaps in processed runs

**Cause:** Failures during processing; check failure logs.

**Solution:**
```bash
# 1. Check failure logs
cat /var/lib/run_record_archiver/import_failures.log
cat /var/lib/run_record_archiver/migrate_failures.log

# 2. Retry failures
./run_archiver.sh config.yaml --retry-failed-import
./run_archiver.sh config.yaml --retry-failed-migrate

# 3. Verify gaps filled
./run_archiver.sh config.yaml --report-status --compare-state
```

---

### Symptom: State file missing

**Cause:** First run or file deleted.

**Solution:**
```bash
# Normal on first run - archiver will create it
# If deleted accidentally, recover from data sources:
./run_archiver.sh config.yaml --recover-import-state
./run_archiver.sh config.yaml --recover-migrate-state
```

---

## Known Issues and Workarounds

### Issue: Concurrent execution despite lock

**Symptoms:** Two archiver instances running simultaneously.

**Cause:** Lock file on NFS mount with stale file handles.

**Workaround:**
```bash
# Use local filesystem for lock file
vim config.yaml
# Update: app.lock_file: "/var/run/archiver.lock"
```

---

### Issue: Large runs timeout during upload

**Symptoms:** Timeout errors for runs > 100 MB.

**Workaround:**
```bash
# Increase timeout
vim config.yaml
# Update: ucon_db.timeout_seconds: 300
```

---

### Issue: FilesystemDB permissions after import

**Symptoms:** Permission errors accessing artdaqDB files.

**Workaround:**
```bash
# Ensure umask allows group read
umask 0022
./run_archiver.sh config.yaml
```

---

## Getting Help

### Before Requesting Help

Gather this information:

1. **Error message** (exact text from logs)
2. **Exit code** (from `echo $?` after archiver exits)
3. **Configuration** (sanitized - remove passwords):
   ```bash
   cat config.yaml | sed 's/password:.*/password: REDACTED/g'
   ```
4. **Environment**:
   ```bash
   python3 --version
   echo $PYTHONPATH
   echo $LD_LIBRARY_PATH
   uname -a
   ```
5. **Relevant log excerpt** (last 100 lines with debug enabled):
   ```bash
   tail -100 /var/lib/run_record_archiver/archiver.log
   ```

### Support Channels

1. **Documentation**: Review all documentation in `run_record_archiver/` and `documentation/`
2. **FAQ**: Check FAQ.md for common questions
3. **Issue Tracker**: Report bugs with full details
4. **Email**: Contact archiver maintainers with gathered information

---

**Related Documentation:**
- [Deployment Guide](DEPLOYMENT_GUIDE.md) - Installation and setup
- [State Management Guide](STATE_MANAGEMENT_GUIDE.md) - State recovery procedures
- [Operations Manual](OPERATIONS_MANUAL.md) - Daily operations and monitoring
- [Configuration Guide](../run_record_archiver/config.md) - Complete configuration reference
- [Exit Codes Reference](EXIT_CODES.md) - Detailed exit code documentation

**Last Updated:** 2025-10-24
