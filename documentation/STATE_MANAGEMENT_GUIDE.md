# State Management Guide - Run Record Archiver

## Table of Contents

- [Overview](#overview)
- [State File Concepts](#state-file-concepts)
  - [Last Contiguous Run](#last-contiguous-run)
  - [Last Attempted Run](#last-attempted-run)
  - [Incremental Mode](#incremental-mode)
- [State File Structure](#state-file-structure)
- [Failure Log Structure](#failure-log-structure)
- [State Tracking During Execution](#state-tracking-during-execution)
- [State Recovery](#state-recovery)
  - [When to Recover State](#when-to-recover-state)
  - [Import State Recovery](#import-state-recovery)
  - [Migration State Recovery](#migration-state-recovery)
- [Manual State Management](#manual-state-management)
- [Common Scenarios](#common-scenarios)
- [Best Practices](#best-practices)
- [Troubleshooting State Issues](#troubleshooting-state-issues)

---

## Overview

The Run Record Archiver uses **state files** to track processing progress and enable incremental execution. State tracking ensures:

1. **No duplicate processing**: Runs already archived are skipped
2. **Resume capability**: Processing can resume after interruption
3. **Gap prevention**: Maintains contiguous run sequences
4. **Failure tracking**: Records which runs failed for retry

There are **two independent state tracking systems**:

- **Import State**: Tracks filesystem → artdaqDB import progress
- **Migration State**: Tracks artdaqDB → UconDB migration progress

Each system maintains:
- **State file** (JSON): Stores progress markers
- **Failure log** (text): Lists runs that failed processing

---

## State File Concepts

### Last Contiguous Run

**Definition:** The highest run number in an unbroken sequence starting from the lowest run.

**Purpose:** Ensures no gaps in the archival sequence. Incremental mode processes from `last_contiguous_run + 1`.

**Example 1: No gaps**
```
Available runs: [100, 101, 102, 103, 104, 105]
Last contiguous run: 105
```

**Example 2: With gap**
```
Available runs: [100, 101, 102, 105, 106, 107]
                              ↑ GAP
Last contiguous run: 102  (stops at first gap)
```

**Example 3: Multiple gaps**
```
Available runs: [100, 101, 103, 104, 106, 107]
                           ↑         ↑ GAPS
Last contiguous run: 101  (stops at first gap)
```

**Algorithm:**
```python
sorted_runs = sorted(available_runs)
last_contiguous = sorted_runs[0]

for i in range(1, len(sorted_runs)):
    if sorted_runs[i] == last_contiguous + 1:
        last_contiguous = sorted_runs[i]
    else:
        break  # Stop at first gap
```

---

### Last Attempted Run

**Definition:** The highest run number that has been attempted for processing, regardless of success or failure.

**Purpose:** Tracks the "high water mark" of processing attempts. Runs beyond this number are considered "not yet attempted."

**Example:**
```
Processed successfully: [100, 101, 102, 105, 106]
Failed processing: [103, 104]
Last attempted run: 106  (highest attempted, regardless of outcome)
```

**Usage:**
- Determines which runs should be in the failure log
- Prevents failure log from growing unbounded with future runs
- Used with `last_contiguous_run` to calculate incremental start point

---

### Incremental Mode

**Definition:** Processing mode that only handles runs newer than the last processing attempt.

**Start Point Calculation:**
```python
start_run = max(last_contiguous_run, last_attempted_run)
# Process runs > start_run
```

**Example:**
```
last_contiguous_run: 102
last_attempted_run: 107
Incremental start: 107  (max of 102 and 107)
→ Next run: Process runs >= 108
```

**Why both values?**
- `last_contiguous_run` tracks successful sequence
- `last_attempted_run` prevents re-attempting recent failures
- Taking max ensures we don't reprocess recent attempts

**Usage:**
```bash
# Run in incremental mode
./run_archiver.sh config.yaml --incremental

# Incremental with stage selection
./run_archiver.sh config.yaml --import-only --incremental
./run_archiver.sh config.yaml --migrate-only --incremental
```

---

## State File Structure

### Format: JSON

**Location:**
- Import state: `${work_dir}/importer_state.json`
- Migration state: `${work_dir}/migrator_state.json`

**Schema:**
```json
{
  "last_contiguous_run": 12500,
  "last_attempted_run": 12550
}
```

**Field Descriptions:**

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `last_contiguous_run` | integer | Highest run in unbroken sequence | 12500 |
| `last_attempted_run` | integer | Highest run attempted (success or fail) | 12550 |

**Initial State (empty or first run):**
```json
{
  "last_contiguous_run": 0,
  "last_attempted_run": 0
}
```

### State File Locations

Configured in `config.yaml`:

```yaml
app:
    work_dir: "/var/lib/run_record_archiver"
    import_state_file: "${work_dir}/importer_state.json"
    migrate_state_file: "${work_dir}/migrator_state.json"
```

**Example paths:**
```
/var/lib/run_record_archiver/
├── importer_state.json      # Import progress
├── import_failures.log      # Import failure log
├── migrator_state.json      # Migration progress
├── migrate_failures.log     # Migration failure log
└── .archiver.lock           # Execution lock
```

---

## Failure Log Structure

### Format: Plain Text (one run number per line)

**Location:**
- Import failures: `${work_dir}/import_failures.log`
- Migration failures: `${work_dir}/migrate_failures.log`

**Example:**
```
12345
12347
12349
12352
```

**Characteristics:**
- One integer per line (run number)
- Sorted numerically
- Duplicates automatically removed
- Empty if no failures

### Failure Log Population

**During Normal Execution:**
```python
# When a run fails:
if processing_failed:
    append_to_failure_log(failure_log, [run_number])
```

**During State Recovery:**
```python
# Runs in source but not in destination:
missing_runs = source_runs - destination_runs

# Only up to last_attempted_run:
missing_runs = [r for r in missing_runs if r <= last_attempted_run]

# Write to failure log:
write_failure_log(failure_log, missing_runs)
```

**Retry Operations:**
```bash
# Reads failure log, attempts each run
./run_archiver.sh config.yaml --retry-failed-import

# Successfully processed runs removed from log
# Still-failing runs remain in log
```

---

## State Tracking During Execution

### Normal Execution Flow

**1. Load Current State:**
```python
state = read_state(state_file)
last_contiguous = state.get('last_contiguous_run', 0)
last_attempted = state.get('last_attempted_run', 0)
```

**2. Determine Runs to Process:**
```python
if incremental_mode:
    start_run = max(last_contiguous, last_attempted)
    runs_to_process = [r for r in available_runs if r > start_run]
else:
    runs_to_process = all_available_runs
```

**3. Process Runs:**
```python
successful_runs = []
failed_runs = []

for run in runs_to_process:
    if process_run(run):
        successful_runs.append(run)
    else:
        failed_runs.append(run)
```

**4. Update State:**
```python
# Update contiguous run (maintains sequence)
update_contiguous_run_state(state_file, successful_runs)

# Update attempted run (high water mark)
update_attempted_run_state(state_file, all_attempted_runs)

# Log failures
append_to_failure_log(failure_log, failed_runs)
```

### State Update Example

**Before execution:**
```json
{
  "last_contiguous_run": 100,
  "last_attempted_run": 100
}
```

**Processing:**
```
Attempted: [101, 102, 103, 104, 105]
Successful: [101, 102, 104, 105]
Failed: [103]
```

**After execution:**
```json
{
  "last_contiguous_run": 102,  // Stopped at gap (103 failed)
  "last_attempted_run": 105    // Highest attempted
}
```

**Failure log:**
```
103
```

---

## State Recovery

### When to Recover State

**Recover state when:**

1. **State files lost or deleted**
   ```bash
   ls /var/lib/run_record_archiver/*.json
   # Files missing
   ```

2. **State files corrupted**
   ```bash
   cat /var/lib/run_record_archiver/importer_state.json
   # Invalid JSON or unexpected values
   ```

3. **Runs processed outside archiver**
   - Manual database insertion
   - External tools used
   - State tracking out of sync

4. **Suspected state inconsistency**
   ```bash
   # Compare state with actual data
   ./run_archiver.sh config.yaml --report-status --compare-state
   ```

5. **Starting fresh tracking on existing data**
   - New deployment over existing databases
   - Want to rebuild state from scratch

**When NOT to recover:**
- State files are current and accurate
- Only a few runs failed (use `--retry-failed-*` instead)
- Regular operation with no issues

---

### Import State Recovery

**Purpose:** Rebuild import state by comparing filesystem with artdaqDB.

**Command:**
```bash
./run_archiver.sh config.yaml --recover-import-state
```

**What It Does:**

1. **Scans filesystem** for all available run records
2. **Queries artdaqDB** for all archived runs
3. **Calculates last_contiguous_run**:
   - Finds highest run in unbroken sequence in artdaqDB
4. **Calculates last_attempted_run**:
   - Highest run number in artdaqDB
5. **Identifies missing runs**:
   - Runs in filesystem but NOT in artdaqDB
   - Only up to `last_attempted_run` (future runs excluded)
6. **Writes state files**:
   - `importer_state.json` with calculated values
   - `import_failures.log` with missing runs

**Example Output:**
```
======================================================================
IMPORT STATE RECOVERY
======================================================================
Scanning filesystem for run records...
Found 523 runs in filesystem

Querying artdaqDB for available runs...
Found 510 runs in artdaqDB

Last attempted run: 12550
Last contiguous run: 12498

Found 13 missing runs to add to failure log
✓ Written import_state.json
✓ Written import_failure.log with 13 runs

======================================================================
IMPORT STATE RECOVERY COMPLETE
  Filesystem runs: 523
  ArtdaqDB runs: 510
  Last contiguous: 12498
  Last attempted: 12550
  Missing runs: 13
  Missing runs (preview): [12345, 12347, 12349, ...]
======================================================================
```

**After Recovery:**
```bash
# Review state
cat /var/lib/run_record_archiver/importer_state.json
cat /var/lib/run_record_archiver/import_failures.log

# Retry failures
./run_archiver.sh config.yaml --retry-failed-import

# Continue with incremental mode
./run_archiver.sh config.yaml --import-only --incremental
```

---

### Migration State Recovery

**Purpose:** Rebuild migration state by comparing artdaqDB with UconDB.

**Command:**
```bash
./run_archiver.sh config.yaml --recover-migrate-state
```

**What It Does:**

1. **Queries artdaqDB** for all archived runs
2. **Queries UconDB** for all migrated runs
3. **Calculates last_contiguous_run**:
   - Finds highest run in unbroken sequence in UconDB
4. **Calculates last_attempted_run**:
   - Highest run number in UconDB
5. **Identifies missing runs**:
   - Runs in artdaqDB but NOT in UconDB
   - Only up to `last_attempted_run`
6. **Writes state files**:
   - `migrator_state.json` with calculated values
   - `migrate_failures.log` with missing runs

**Example Output:**
```
======================================================================
MIGRATION STATE RECOVERY
======================================================================
Querying artdaqDB for available runs...
Found 510 runs in artdaqDB

Querying UconDB for migrated runs...
Found 495 runs in UconDB

Last attempted run: 12550
Last contiguous run: 12490

Found 15 missing runs to add to failure log
✓ Written migrator_state.json
✓ Written migrate_failure.log with 15 runs

======================================================================
MIGRATION STATE RECOVERY COMPLETE
  ArtdaqDB runs: 510
  UconDB runs: 495
  Last contiguous: 12490
  Last attempted: 12550
  Missing runs: 15
  Missing runs (preview): [12345, 12348, 12351, ...]
======================================================================
```

**After Recovery:**
```bash
# Review state
cat /var/lib/run_record_archiver/migrator_state.json
cat /var/lib/run_record_archiver/migrate_failures.log

# Retry failures
./run_archiver.sh config.yaml --retry-failed-migrate

# Continue with incremental mode
./run_archiver.sh config.yaml --migrate-only --incremental
```

---

## Manual State Management

### Inspecting State Files

```bash
# View import state
cat /var/lib/run_record_archiver/importer_state.json | python3 -m json.tool

# View migration state
cat /var/lib/run_record_archiver/migrator_state.json | python3 -m json.tool

# Count failures
wc -l /var/lib/run_record_archiver/import_failures.log
wc -l /var/lib/run_record_archiver/migrate_failures.log

# View specific failures
head -20 /var/lib/run_record_archiver/import_failures.log
```

### Manually Editing State Files

**⚠️ WARNING: Manual editing can break state tracking. Use with caution.**

**When manual editing is appropriate:**
- Emergency recovery scenarios
- Known data inconsistencies
- Directed by archiver developers

**Procedure:**

```bash
# 1. Stop archiver
sudo systemctl stop run-record-archiver.timer

# 2. Backup current state
cp /var/lib/run_record_archiver/importer_state.json \
   /var/lib/run_record_archiver/importer_state.json.backup

# 3. Edit state file
vim /var/lib/run_record_archiver/importer_state.json

# Example: Reset to specific run
{
  "last_contiguous_run": 12000,
  "last_attempted_run": 12000
}

# 4. Validate JSON syntax
python3 -m json.tool /var/lib/run_record_archiver/importer_state.json

# 5. Test with report
./run_archiver.sh config.yaml --report-status --compare-state

# 6. Restart archiver
sudo systemctl start run-record-archiver.timer
```

### Resetting State (Start Fresh)

```bash
# DANGER: This discards all tracking

# 1. Stop archiver
sudo systemctl stop run-record-archiver.timer

# 2. Backup (optional but recommended)
tar -czf state-backup-$(date +%Y%m%d).tar.gz \
    /var/lib/run_record_archiver/*.json \
    /var/lib/run_record_archiver/*.log

# 3. Remove state files
rm /var/lib/run_record_archiver/importer_state.json
rm /var/lib/run_record_archiver/migrator_state.json
rm /var/lib/run_record_archiver/import_failures.log
rm /var/lib/run_record_archiver/migrate_failures.log

# 4. Recover from actual data
./run_archiver.sh config.yaml --recover-import-state
./run_archiver.sh config.yaml --recover-migrate-state

# 5. Restart
sudo systemctl start run-record-archiver.timer
```

---

## Common Scenarios

### Scenario 1: Fresh Deployment

**Situation:** Installing archiver for the first time on existing data.

**Steps:**
```bash
# 1. Deploy archiver
# (Follow DEPLOYMENT_GUIDE.md)

# 2. Recover state from existing data
./run_archiver.sh config.yaml --recover-import-state
./run_archiver.sh config.yaml --recover-migrate-state

# 3. Review recovery results
cat /var/lib/run_record_archiver/importer_state.json
cat /var/lib/run_record_archiver/migrator_state.json

# 4. Process any missing runs
./run_archiver.sh config.yaml --retry-failed-import
./run_archiver.sh config.yaml --retry-failed-migrate

# 5. Enable incremental mode
# (Configure cron or systemd timer with --incremental)
```

---

### Scenario 2: State File Corruption

**Situation:** State file contains invalid JSON or unexpected values.

**Steps:**
```bash
# 1. Check state file
cat /var/lib/run_record_archiver/importer_state.json
# Output: {corrupted data...

# 2. Backup corrupted file
mv /var/lib/run_record_archiver/importer_state.json \
   /var/lib/run_record_archiver/importer_state.json.corrupted

# 3. Recover from actual data
./run_archiver.sh config.yaml --recover-import-state

# 4. Verify recovery
cat /var/lib/run_record_archiver/importer_state.json
```

---

### Scenario 3: Gap in Run Sequence

**Situation:** Some runs failed and created a gap.

**Current state:**
```json
{
  "last_contiguous_run": 12100,
  "last_attempted_run": 12150
}
```

**Failure log:**
```
12101
12103
12107
```

**Steps:**
```bash
# 1. Retry failed runs
./run_archiver.sh config.yaml --retry-failed-import

# 2. Check if gap filled
./run_archiver.sh config.yaml --report-status --compare-state

# 3. If runs still fail, investigate
./run_archiver.sh config.yaml --retry-failed-import -v

# 4. Once gap filled, last_contiguous_run will advance
```

**After successful retry:**
```json
{
  "last_contiguous_run": 12150,  // Advanced past gap
  "last_attempted_run": 12150
}
```

---

### Scenario 4: Manual Database Operations

**Situation:** Runs were imported manually using external tools.

**Steps:**
```bash
# 1. Check current state
./run_archiver.sh config.yaml --report-status --compare-state

# 2. Recover state to reflect manual changes
./run_archiver.sh config.yaml --recover-import-state

# 3. Verify state now accurate
./run_archiver.sh config.yaml --report-status --compare-state

# 4. Continue with normal operations
./run_archiver.sh config.yaml --incremental
```

---

### Scenario 5: Processing Interrupted

**Situation:** Archiver interrupted mid-execution (Ctrl-C, crash, server reboot).

**What happens:**
- Current run completes or fails
- State saved up to interruption point
- Lock file may remain (if crash)

**Steps:**
```bash
# 1. Check if still running
ps aux | grep run_archiver

# 2. Remove stale lock if needed
rm /var/lib/run_record_archiver/.archiver.lock

# 3. Check state
cat /var/lib/run_record_archiver/importer_state.json

# 4. Resume with incremental mode
./run_archiver.sh config.yaml --incremental

# 5. Retry any failures
./run_archiver.sh config.yaml --retry-failed-import
```

---

## Best Practices

### 1. Use Incremental Mode for Scheduled Runs

```bash
# Cron or systemd timer should use --incremental
./run_archiver.sh config.yaml --incremental
```

**Benefits:**
- Processes only new runs
- Faster execution
- Lower resource usage
- Prevents duplicate processing

---

### 2. Backup State Files Regularly

```bash
# Weekly backup
0 0 * * 0 tar -czf /backup/archiver-state-$(date +\%Y\%m\%d).tar.gz \
    /var/lib/run_record_archiver/*.json \
    /var/lib/run_record_archiver/*.log
```

---

### 3. Monitor Failure Logs

```bash
# Check failure count
wc -l /var/lib/run_record_archiver/import_failures.log
wc -l /var/lib/run_record_archiver/migrate_failures.log

# Alert if failures exceed threshold
if [ $(wc -l < /var/lib/run_record_archiver/import_failures.log) -gt 50 ]; then
    echo "Alert: High failure count"
fi
```

---

### 4. Use --compare-state for Validation

```bash
# Periodically verify state consistency
./run_archiver.sh config.yaml --report-status --compare-state
```

**Checks:**
- State vs actual data discrepancies
- Gap analysis
- Failure log accuracy

---

### 5. Recover State After External Changes

```bash
# After manual database operations
./run_archiver.sh config.yaml --recover-import-state
./run_archiver.sh config.yaml --recover-migrate-state
```

---

### 6. Don't Manually Edit Unless Necessary

- Prefer `--recover-*-state` over manual editing
- Manual edits can introduce inconsistencies
- Always backup before manual changes

---

## Troubleshooting State Issues

### Issue: Runs processed repeatedly

**Symptom:**
```
[Import] [Run 12345] Configuration 12345/BootDAQ is already archived
```

**Diagnosis:**
```bash
# Check if incremental mode used
# Check state file values
cat /var/lib/run_record_archiver/importer_state.json

# Compare with actual data
./run_archiver.sh config.yaml --report-status --compare-state
```

**Solution:**
```bash
# Recover state
./run_archiver.sh config.yaml --recover-import-state

# Use incremental mode
./run_archiver.sh config.yaml --incremental
```

---

### Issue: Incremental mode processes too many runs

**Symptom:** Incremental mode processes runs that should be skipped.

**Diagnosis:**
```bash
# Check state values
cat /var/lib/run_record_archiver/importer_state.json

# last_contiguous_run or last_attempted_run too low
```

**Solution:**
```bash
# Recover state from actual data
./run_archiver.sh config.yaml --recover-import-state
```

---

### Issue: Gaps not filling

**Symptom:** Failure log has runs, but retries don't succeed.

**Diagnosis:**
```bash
# Check failure log
cat /var/lib/run_record_archiver/import_failures.log

# Try retry with debug
./run_archiver.sh config.yaml --retry-failed-import -v
```

**Solution:**
```bash
# Review logs for specific errors
# Fix underlying issue (permissions, connectivity, etc.)
# Retry again
./run_archiver.sh config.yaml --retry-failed-import
```

---

### Issue: State file won't write

**Symptom:**
```
Failed to write state file: Permission denied
```

**Solution:**
```bash
# Check permissions
ls -la /var/lib/run_record_archiver

# Fix ownership
sudo chown -R archiver:archiver /var/lib/run_record_archiver

# Fix permissions
sudo chmod 755 /var/lib/run_record_archiver
sudo chmod 644 /var/lib/run_record_archiver/*.json
```

---

**Related Documentation:**
- [Deployment Guide](DEPLOYMENT_GUIDE.md) - Initial setup and configuration
- [Operations Manual](OPERATIONS_MANUAL.md) - Daily operations and monitoring
- [Troubleshooting Guide](TROUBLESHOOTING_GUIDE.md) - Error resolution
- [Command-Line Reference](../run_record_archiver/main.md) - All CLI options
- [File Formats](FILE_FORMATS.md) - Detailed file format specifications

**Last Updated:** 2025-10-24
