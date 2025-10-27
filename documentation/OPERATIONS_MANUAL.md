# Operations Manual - Run Record Archiver

## Table of Contents

- [Overview](#overview)
- [Daily Operations](#daily-operations)
  - [Monitoring Checklist](#monitoring-checklist)
  - [Log Review Procedures](#log-review-procedures)
  - [Status Report Generation](#status-report-generation)
  - [Routine Health Checks](#routine-health-checks)
- [Execution Patterns](#execution-patterns)
  - [Full vs Incremental Runs](#full-vs-incremental-runs)
  - [Scheduled Execution](#scheduled-execution)
  - [Manual Execution](#manual-execution)
  - [Stage-Specific Execution](#stage-specific-execution)
- [Monitoring](#monitoring)
  - [Key Metrics](#key-metrics)
  - [Log Patterns to Watch](#log-patterns-to-watch)
  - [Alerting Configuration](#alerting-configuration)
  - [Dashboard Recommendations](#dashboard-recommendations)
- [Performance Tuning](#performance-tuning)
  - [Parallel Workers Configuration](#parallel-workers-configuration)
  - [Batch Size Optimization](#batch-size-optimization)
  - [Database Optimization](#database-optimization)
  - [Network Optimization](#network-optimization)
  - [CLI Tools vs API](#cli-tools-vs-api)
- [Log Analysis](#log-analysis)
  - [Reading Archiver Logs](#reading-archiver-logs)
  - [Identifying Patterns](#identifying-patterns)
  - [Debug Mode Usage](#debug-mode-usage)
  - [Log Rotation Management](#log-rotation-management)
- [Graceful Shutdown](#graceful-shutdown)
  - [Normal Shutdown Procedure](#normal-shutdown-procedure)
  - [Immediate Shutdown](#immediate-shutdown)
  - [Verifying Shutdown Completion](#verifying-shutdown-completion)
  - [Resuming After Shutdown](#resuming-after-shutdown)
- [Emergency Procedures](#emergency-procedures)
  - [Stuck Processes](#stuck-processes)
  - [Full Disk Recovery](#full-disk-recovery)
  - [Database Unavailability](#database-unavailability)
  - [Network Outages](#network-outages)
  - [Crash Recovery](#crash-recovery)
- [Routine Maintenance](#routine-maintenance)
  - [Log Management](#log-management)
  - [State File Backup](#state-file-backup)
  - [Failure Log Review](#failure-log-review)
  - [Configuration Updates](#configuration-updates)
  - [Dependency Updates](#dependency-updates)
- [Capacity Planning](#capacity-planning)
  - [Disk Space Requirements](#disk-space-requirements)
  - [Memory Requirements](#memory-requirements)
  - [Network Bandwidth](#network-bandwidth)
  - [Database Growth](#database-growth)
- [Backup and Restore](#backup-and-restore)
  - [What to Backup](#what-to-backup)
  - [Backup Frequency](#backup-frequency)
  - [Restore Procedures](#restore-procedures)

---

## Overview

This manual provides practical guidance for day-to-day operation of the Run Record Archiver. It covers routine monitoring, performance optimization, troubleshooting, and maintenance procedures.

**Target Audience:**
- System operators running scheduled archiver jobs
- On-call engineers responding to alerts
- Administrators managing the archiver infrastructure

**Related Documentation:**
- [Deployment Guide](DEPLOYMENT_GUIDE.md) - Installation and setup
- [Troubleshooting Guide](TROUBLESHOOTING_GUIDE.md) - Error resolution
- [State Management Guide](STATE_MANAGEMENT_GUIDE.md) - State recovery procedures
- [Configuration Guide](../run_record_archiver/config.md) - Configuration reference

---

## Daily Operations

### Monitoring Checklist

Perform these checks daily to ensure healthy archiver operation:

#### 1. Execution Status

```bash
# Check if archiver completed successfully (systemd)
sudo systemctl status run-record-archiver.service
sudo journalctl -u run-record-archiver.service --since today

# Check if archiver completed successfully (cron)
tail -50 /var/log/run-record-archiver-cron.log

# Verify exit code from last run
echo $?  # Should be 0 for success
```

**Expected:** Exit code 0, no error messages in logs.

#### 2. Processing Progress

```bash
# Check state files for progress
cat /var/lib/run_record_archiver/importer_state.json
cat /var/lib/run_record_archiver/migrator_state.json

# Example output:
# {"last_contiguous_run": 12500, "last_attempted_run": 12550}
```

**Expected:** `last_contiguous_run` and `last_attempted_run` advancing daily.

#### 3. Failure Log Status

```bash
# Count failures
wc -l /var/lib/run_record_archiver/import_failures.log
wc -l /var/lib/run_record_archiver/migrate_failures.log

# View recent failures
tail -20 /var/lib/run_record_archiver/import_failures.log
```

**Expected:** Low failure count (< 5% of runs processed).

**Action Required If:**
- Failure count > 50: Investigate common failure patterns
- Failure count growing rapidly: Check connectivity and permissions

#### 4. Disk Space

```bash
# Check work directory disk usage
df -h /var/lib/run_record_archiver

# Check log file sizes
ls -lh /var/lib/run_record_archiver/*.log*

# Check temporary directory
df -h /tmp
```

**Expected:** > 20% free space available.

**Action Required If:**
- < 20% free: Plan log cleanup or disk expansion
- < 10% free: Immediate cleanup required

#### 5. Lock File Status

```bash
# Check for stale locks (should not exist if archiver not running)
ls -la /var/lib/run_record_archiver/.archiver.lock

# If exists, check if process is actually running
ps aux | grep run_record_archiver
```

**Expected:** No lock file when archiver not scheduled to run.

**Action Required If:**
- Lock file exists but no process: Remove stale lock
- Multiple processes found: Investigate scheduling conflict

---

### Log Review Procedures

#### Quick Review (5 minutes)

```bash
# Check for errors in last run
grep -i "error\|critical\|exception" /var/lib/run_record_archiver/archiver.log | tail -20

# Check for warnings
grep -i "warning" /var/lib/run_record_archiver/archiver.log | tail -20

# Check processing summary
grep "EXECUTION COMPLETED" /var/lib/run_record_archiver/archiver.log | tail -5
```

#### Detailed Review (15 minutes)

```bash
# Review last execution in detail
grep "Run Record Archiver Starting" /var/lib/run_record_archiver/archiver.log | tail -1
# Copy timestamp, then:
sed -n '/2025-10-24 03:00:00/,/EXECUTION COMPLETED/p' /var/lib/run_record_archiver/archiver.log

# Check for patterns indicating issues:
# - Repeated connection errors
# - Consistent failures on specific runs
# - Performance degradation (slow processing)
```

#### Weekly Review (30 minutes)

```bash
# Generate comprehensive weekly report
./run_archiver.sh config.yaml --report-status --compare-state > weekly_report_$(date +%Y%m%d).txt

# Analyze trends:
# - Processing rate (runs per hour)
# - Failure rate (% of runs failing)
# - Retry success rate
# - Gap accumulation

# Review state comparison output for inconsistencies
```

---

### Status Report Generation

The status report provides a comprehensive view of run availability across all data sources.

#### Generate Basic Report

```bash
# Quick status check
./run_archiver.sh config.yaml --report-status
```

**Output Includes:**
- Total runs in filesystem, artdaqDB, and UconDB
- Run ranges (oldest to newest)
- Gap analysis (missing runs within ranges)
- Recommendations for which stage to run

#### Generate Report with State Comparison

```bash
# Compare with saved state files
./run_archiver.sh config.yaml --report-status --compare-state

# Shorter form (equivalent):
./run_archiver.sh config.yaml --compare-state
```

**Additional Output:**
- Import stage state (last contiguous run, failures)
- Migration stage state (last contiguous run, failures)
- Runs missing from expected range
- New runs available since last state update

#### Interpreting Report Output

**Example Output:**
```
======================================================================
RUN RECORD ARCHIVER - STATUS REPORT
======================================================================

DATA SOURCE SUMMARY
======================================================================

FILESYSTEM (Source)
----------------------------------------------------------------------
  Location:        /daq/run_records
  Total Runs:      523
  Range:           12000 to 12522
  Contiguous:      12000-12100, 12102-12522
  Gaps:            12101

ARTDAQDB (Intermediate Storage)
----------------------------------------------------------------------
  Database URI:    filesystemdb:///data/artdaqdb_archive
  Total Runs:      510
  Range:           12000 to 12522
  Contiguous:      12000-12100, 12102-12498
  Gaps:            12101, 12499-12522

UCONDB (Long-term Storage)
----------------------------------------------------------------------
  Server URL:      https://ucondb.example.com:9443/instance/app
  Folder/Object:   production/configuration
  Total Runs:      495
  Range:           12000 to 12498
  Contiguous:      12000-12100, 12102-12498
  Gaps:            12101

======================================================================
RECOMMENDATIONS
======================================================================
1. Run IMPORTER: 13 run(s) on filesystem not in artdaqDB (range: 12499-12522)
2. Run MIGRATOR: 15 run(s) in artdaqDB not in UconDB (range: 12499-12522)
3. WARNING: 1 run(s) failed in all stages (12101)
```

**Analysis:**
- **Filesystem leads artdaqDB**: Import stage needs to run (runs 12499-12522)
- **ArtdaqDB leads UconDB**: Migration stage needs to run
- **Gap in all stages (12101)**: Permanent failure or data quality issue requiring investigation

---

### Routine Health Checks

Perform these checks to ensure optimal operation:

#### Database Connectivity

```bash
# Test ArtdaqDB connection
python3 << 'EOF'
from run_record_archiver.config import Config
from run_record_archiver.clients.artdaq import ArtdaqDBClient

config = Config.from_file('config.yaml')
client = ArtdaqDBClient(database_uri=config.artdaq_db.database_uri)
runs = client.get_archived_runs()
print(f"✓ ArtdaqDB: {len(runs)} runs accessible")
EOF

# Test UconDB connection
python3 << 'EOF'
from run_record_archiver.config import Config
from run_record_archiver.clients.ucondb import UconDBClient

config = Config.from_file('config.yaml')
client = UconDBClient(config.ucon_db)
runs = client.get_existing_runs()
print(f"✓ UconDB: {len(runs)} runs accessible")
EOF
```

#### File System Access

```bash
# Verify read access to source
ls -la /daq/run_records | head -20

# Verify write access to work directory
touch /var/lib/run_record_archiver/test_write && rm /var/lib/run_record_archiver/test_write
echo "✓ Work directory writable"

# Check for new runs
find /daq/run_records -maxdepth 1 -type d -name "[0-9]*" -mtime -1 | wc -l
echo "new runs in last 24 hours"
```

#### Resource Utilization

```bash
# Check memory usage during execution
ps aux | grep run_archiver | awk '{print $4, $6, $11}'
# Output: %MEM RSS(KB) COMMAND

# Check CPU usage
top -b -n 1 | grep run_archiver

# Check I/O wait
iostat -x 5 2 | grep -A 1 "Device"
```

---

## Execution Patterns

### Full vs Incremental Runs

#### Full Run

**Purpose:** Process all available runs regardless of state.

**When to Use:**
- Initial deployment or re-deployment
- After state file corruption or loss
- After manual database cleanup
- Testing or validation purposes

**Command:**
```bash
# Full pipeline (both stages)
./run_archiver.sh config.yaml

# Import stage only
./run_archiver.sh config.yaml --import-only

# Migration stage only
./run_archiver.sh config.yaml --migrate-only
```

**Characteristics:**
- Processes all runs in filesystem or database
- Ignores state tracking
- Longer execution time
- Higher resource usage
- May attempt duplicate processing (safely skipped by databases)

**Risk:** Can overwhelm databases with duplicate insertion attempts.

#### Incremental Run

**Purpose:** Process only new runs since last successful execution.

**When to Use:**
- Scheduled regular execution (hourly, daily)
- Production operations
- Resource-constrained environments

**Command:**
```bash
# Incremental pipeline (both stages)
./run_archiver.sh config.yaml --incremental

# Import stage only (incremental)
./run_archiver.sh config.yaml --import-only --incremental

# Migration stage only (incremental)
./run_archiver.sh config.yaml --migrate-only --incremental
```

**Characteristics:**
- Starts from `max(last_contiguous_run, last_attempted_run) + 1`
- Only processes new runs
- Fast execution
- Low resource usage
- Safe for frequent scheduled execution

**Best Practice:** Always use `--incremental` for scheduled runs.

---

### Scheduled Execution

#### Recommended Schedule

**Hourly Incremental (Most Common):**
```bash
# Cron: Every hour at 5 minutes past
5 * * * * archiver ${HOME}/run_record_archiver/run_archiver.sh config.yaml --incremental

# Systemd timer: OnCalendar=hourly
```

**Daily Full Status Report:**
```bash
# Cron: Daily at 6 AM
0 6 * * * archiver ${HOME}/run_record_archiver/run_archiver.sh config.yaml --report-status --compare-state >> /var/log/archiver-daily-report.log

# Systemd timer: OnCalendar=daily
```

**Weekly Failure Retry:**
```bash
# Cron: Every Sunday at 2 AM
0 2 * * 0 archiver ${HOME}/run_record_archiver/run_archiver.sh config.yaml --retry-failed-import
0 3 * * 0 archiver ${HOME}/run_record_archiver/run_archiver.sh config.yaml --retry-failed-migrate
```

#### Systemd Timer Configuration

**Service File:** `/etc/systemd/system/run-record-archiver.service`
```ini
[Unit]
Description=Run Record Archiver
After=network-online.target

[Service]
Type=oneshot
User=archiver
WorkingDirectory=${HOME}/run_record_archiver
ExecStart=${HOME}/run_record_archiver/run_archiver.sh config.yaml --incremental
StandardOutput=journal
StandardError=journal

# Resource limits
MemoryMax=4G
CPUQuota=200%
TimeoutStartSec=3600
```

**Timer File:** `/etc/systemd/system/run-record-archiver.timer`
```ini
[Unit]
Description=Run Record Archiver Timer

[Timer]
OnCalendar=hourly
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
```

**Enable and Monitor:**
```bash
# Enable timer
sudo systemctl enable run-record-archiver.timer
sudo systemctl start run-record-archiver.timer

# Check timer status
sudo systemctl list-timers run-record-archiver.timer

# View execution logs
sudo journalctl -u run-record-archiver.service -f
```

---

### Manual Execution

#### Interactive Execution

```bash
# Run with live output
./run_archiver.sh config.yaml --incremental

# Run with debug logging
./run_archiver.sh config.yaml --incremental -v

# Run and log to file
./run_archiver.sh config.yaml --incremental 2>&1 | tee manual_run_$(date +%Y%m%d_%H%M%S).log
```

#### Background Execution

```bash
# Run in background with nohup
nohup ./run_archiver.sh config.yaml --incremental > /tmp/archiver.out 2>&1 &

# Check progress
tail -f /tmp/archiver.out

# Check if still running
ps aux | grep run_archiver
```

**Note:** Background execution should only be used for testing. Use systemd or cron for production.

---

### Stage-Specific Execution

#### Import Stage Only

**Use Cases:**
- ArtdaqDB maintenance window (UconDB unavailable)
- Backfilling filesystem runs into artdaqDB
- Testing import logic changes

**Commands:**
```bash
# Incremental import
./run_archiver.sh config.yaml --import-only --incremental

# Full import (all runs)
./run_archiver.sh config.yaml --import-only

# Retry failed imports
./run_archiver.sh config.yaml --retry-failed-import
```

#### Migration Stage Only

**Use Cases:**
- UconDB catch-up after downtime
- Backfilling artdaqDB runs into UconDB
- Testing migration logic changes

**Commands:**
```bash
# Incremental migration
./run_archiver.sh config.yaml --migrate-only --incremental

# Migration with validation
./run_archiver.sh config.yaml --migrate-only --incremental --validate

# Retry failed migrations
./run_archiver.sh config.yaml --retry-failed-migrate
```

**Best Practice:** Use `--validate` flag when migrating critical runs to ensure integrity.

---

## Monitoring

### Key Metrics

Monitor these metrics for operational health:

#### 1. Processing Rate Metrics

**Metrics to Track:**
- `archiver.import.runs_processed` - Runs imported per execution
- `archiver.import.runs_failed` - Import failures per execution
- `archiver.import.duration_seconds` - Time to complete import stage
- `archiver.migrate.runs_processed` - Runs migrated per execution
- `archiver.migrate.runs_failed` - Migration failures per execution
- `archiver.migrate.duration_seconds` - Time to complete migration stage

**Carbon/Graphite Integration:**

The archiver posts metrics automatically when `carbon.enabled: true` in config:

```yaml
carbon:
    enabled: true
    host: "carbon.example.com"
    port: 2003
    metric_prefix: "exp.run_archiver.prod"
```

**Metric Format:**
```
exp.run_archiver.prod.import.runs_processed 45 1698345600
exp.run_archiver.prod.import.duration_seconds 823.5 1698345600
exp.run_archiver.prod.migrate.runs_processed 42 1698346200
```

#### 2. Database Health Metrics

**ArtdaqDB:**
- Connection latency
- Query response time
- Available disk space (if FilesystemDB)
- Collection size (if MongoDB)

**UconDB:**
- API response time
- Upload success rate
- MD5 verification failures
- Server availability

#### 3. System Resource Metrics

**Monitor via system tools:**
```bash
# Memory usage
ps aux | awk '/run_archiver/{sum+=$6} END {print "Memory:", sum/1024, "MB"}'

# CPU usage
top -b -n 1 | grep run_archiver | awk '{print "CPU:", $9"%"}'

# Disk I/O
iostat -x 1 5 | grep -A 1 "^Device"

# Network throughput
iftop -t -s 10
```

#### 4. Operational Metrics

Track these manually or via monitoring scripts:

- **Gap accumulation rate:** Gaps discovered per day
- **Failure retry success rate:** % of retried runs that succeed
- **State advancement rate:** Runs added to `last_contiguous_run` per day
- **Log growth rate:** MB of logs generated per day

---

### Log Patterns to Watch

#### Success Indicators

```
✓ EXECUTION COMPLETED SUCCESSFULLY
✓ Run XXXXX imported successfully
✓ Run XXXXX migrated successfully
✓ ArtdaqDB query complete
✓ UconDB query complete
```

#### Warning Patterns

```
WARNING: X run(s) in artdaqDB but not on filesystem
WARNING: High failure count
Retrying run XXXXX in X seconds...
requests.exceptions.Timeout: Read timed out
```

**Action:** Investigate warnings that repeat frequently or affect many runs.

#### Error Patterns

```
ERROR: Failed to connect to database
ERROR: Permission denied
CRITICAL: UNEXPECTED ERROR SUMMARY
ArchiverError: Configuration validation failed
LockExistsError: Another process may be running
```

**Action:** Immediate investigation required.

#### Performance Degradation Indicators

```
# Slow processing (compare with baseline)
Import Stage completed in 3456 seconds  # Baseline: 600 seconds

# High retry rates
Retrying run XXXXX (attempt 3/3)
Retrying run YYYYY (attempt 3/3)

# Database slowness
Querying artdaqDB... (took 45 seconds)  # Baseline: 2 seconds
```

**Action:** Check database performance, network latency, and system resources.

---

### Alerting Configuration

#### Alert Thresholds

**Critical Alerts (immediate response):**
- Exit code ≠ 0 for > 3 consecutive executions
- Failure count > 100 runs
- Lock file exists for > 2 hours
- Disk space < 10%
- Database unreachable for > 30 minutes

**Warning Alerts (review within 24 hours):**
- Failure count > 50 runs
- Execution time > 2x baseline
- No progress in `last_contiguous_run` for > 48 hours
- Disk space < 20%

**Info Alerts (review weekly):**
- Failure count > 10 runs
- Gaps accumulating
- State file not updated for > 24 hours

#### Email Alerting

Configure in `config.yaml`:

```yaml
reporting:
    email:
        enabled: true
        recipient_email: "team@example.com"
        sender_email: "archiver@example.com"
        smtp_host: "smtp.example.com"
        smtp_port: 25
```

**Trigger:** Automatic email sent when runs fail during execution.

#### Slack Alerting

Configure in `config.yaml`:

```yaml
reporting:
    slack:
        enabled: true
        bot_token: "xoxb-your-bot-token"
        channel: "#archiver-alerts"
        mention_users: "U123456,U789012"  # User IDs to @mention
```

**Trigger:** Slack message with @mentions sent when runs fail.

See [slack.md](../run_record_archiver/slack.md) for setup instructions.

#### External Monitoring

**Prometheus Integration (custom):**
```bash
# Export metrics from logs
grep "EXECUTION COMPLETED" archiver.log | \
    awk '{print "archiver_execution_status 0"}' > /var/lib/node_exporter/archiver.prom

# Or from state files
cat /var/lib/run_record_archiver/importer_state.json | \
    jq -r '"archiver_last_contiguous_run{stage=\"import\"} \(.last_contiguous_run)"' \
    > /var/lib/node_exporter/archiver.prom
```

---

### Dashboard Recommendations

#### Graphite/Grafana Dashboard

**Panels to Include:**

1. **Processing Rate**
   - Metric: `archiver.*.runs_processed`
   - Visualization: Line graph (runs/hour)
   - Time range: Last 7 days

2. **Failure Rate**
   - Metric: `archiver.*.runs_failed / (archiver.*.runs_processed + archiver.*.runs_failed)`
   - Visualization: Percentage gauge
   - Threshold: Warning > 5%, Critical > 10%

3. **Execution Duration**
   - Metric: `archiver.*.duration_seconds`
   - Visualization: Line graph with baseline
   - Alert: Duration > 2x baseline

4. **State Progress**
   - Metric: Custom (parse state files)
   - Visualization: Single stat (last_contiguous_run)
   - Trend: Should increase daily

5. **Failure Log Size**
   - Metric: Custom (line count from logs)
   - Visualization: Bar graph
   - Alert: Count > 50

#### Simple Text Dashboard

For environments without Graphite:

```bash
#!/bin/bash
# dashboard.sh - Simple status dashboard

echo "======================================"
echo "Run Record Archiver Dashboard"
echo "Generated: $(date)"
echo "======================================"

echo ""
echo "EXECUTION STATUS"
echo "--------------------------------------"
systemctl status run-record-archiver.service | grep "Active:"
echo ""

echo "STATE TRACKING"
echo "--------------------------------------"
echo "Import State:"
cat /var/lib/run_record_archiver/importer_state.json
echo ""
echo "Migration State:"
cat /var/lib/run_record_archiver/migrator_state.json
echo ""

echo "FAILURE COUNTS"
echo "--------------------------------------"
echo "Import failures: $(wc -l < /var/lib/run_record_archiver/import_failures.log)"
echo "Migration failures: $(wc -l < /var/lib/run_record_archiver/migrate_failures.log)"
echo ""

echo "DISK USAGE"
echo "--------------------------------------"
df -h /var/lib/run_record_archiver | tail -1
echo ""

echo "LAST 5 LOG ENTRIES"
echo "--------------------------------------"
tail -5 /var/lib/run_record_archiver/archiver.log
echo "======================================"
```

Run hourly via cron:
```bash
0 * * * * ${HOME}/run_record_archiver/dashboard.sh > /var/www/html/archiver_status.txt
```

---

## Performance Tuning

### Parallel Workers Configuration

**Parameter:** `app.parallel_workers` in `config.yaml`

#### Determining Optimal Value

**Formula:**
```
optimal_workers = min(CPU_cores, network_bandwidth_limit, database_connection_limit)
```

**Factors:**
- **CPU cores:** 1 worker per core (hyperthreading counts as 0.5 core)
- **Network bandwidth:** 1 worker per 10 Mbps sustained throughput
- **Database connections:** Check database connection pool limits
- **Memory:** 500 MB per worker (approximate)

**Examples:**

**Small System (2 cores, 100 Mbps network):**
```yaml
app:
    parallel_workers: 2
    batch_size: 5
```

**Medium System (8 cores, 1 Gbps network):**
```yaml
app:
    parallel_workers: 8
    batch_size: 10
```

**Large System (32 cores, 10 Gbps network):**
```yaml
app:
    parallel_workers: 16
    batch_size: 20
```

**Note:** With `artdaq_db.use_tools: false` (conftoolp API mode), workers are forced to 1 due to thread-safety limitations.

#### Testing Worker Configuration

```bash
# Test with different worker counts
for workers in 2 4 8 16; do
    echo "Testing with $workers workers..."
    sed -i "s/parallel_workers:.*/parallel_workers: $workers/" config.yaml
    time ./run_archiver.sh config.yaml --import-only --incremental
    echo ""
done
```

Analyze results to find optimal balance between throughput and resource usage.

---

### Batch Size Optimization

**Parameter:** `app.batch_size` in `config.yaml`

**Purpose:** Limits number of runs processed per execution (used in incremental mode).

#### Recommendations

**High-Frequency Execution (hourly):**
```yaml
app:
    batch_size: 5-10  # Process recent runs quickly
```

**Low-Frequency Execution (daily):**
```yaml
app:
    batch_size: 50-100  # Process larger batches
```

**Catch-Up Mode (after downtime):**
```yaml
app:
    batch_size: 200-500  # Maximize throughput
```

**Testing:**
```bash
# Small batch (fast, frequent)
batch_size: 5
# → Good for: Hourly execution, low latency requirements

# Medium batch (balanced)
batch_size: 25
# → Good for: Daily execution, moderate backlog

# Large batch (maximum throughput)
batch_size: 100
# → Good for: Weekly execution, large backlog
```

---

### Database Optimization

#### ArtdaqDB (MongoDB)

**Index Creation:**
```javascript
// Connect to MongoDB
use artdaqdb_archive

// Create index on configuration name (improves query performance)
db.configurations.createIndex({"name": 1})

// Create index on version timestamp
db.configurations.createIndex({"metadata.timestamp": 1})
```

**Connection Pooling:**
```yaml
artdaq_db:
    # Use connection pool for concurrent operations
    database_uri: "mongodb://user:pass@host:port/database?maxPoolSize=20"
```

**Query Optimization:**
- Avoid full collection scans
- Use projection to limit returned fields
- Monitor slow query log

#### ArtdaqDB (FilesystemDB)

**Filesystem Tuning:**
```bash
# Use dedicated partition with optimal settings
mount /dev/sdb1 /data/artdaqdb_archive -o noatime,nodiratime

# Use XFS or ext4 with large directory support
mkfs.xfs -n ftype=1 /dev/sdb1
```

**Permissions:**
```bash
# Ensure proper ownership and permissions
chown -R archiver:archiver /data/artdaqdb_archive
chmod 755 /data/artdaqdb_archive
```

**I/O Scheduling:**
```bash
# Use deadline or noop scheduler for SSDs
echo deadline > /sys/block/sdb/queue/scheduler
```

#### UconDB

**Connection Tuning:**
```yaml
ucon_db:
    timeout_seconds: 60  # Increase for large runs or slow networks
```

**Request Batching:**

UconDB client automatically batches requests. Monitor server load and adjust `parallel_workers` if needed.

**Server-Side Optimization:**

Contact UconDB administrator to:
- Enable response compression
- Optimize database indexes
- Increase connection pool size

---

### Network Optimization

#### Bandwidth Optimization

**Monitor Network Usage:**
```bash
# Real-time bandwidth monitoring
iftop -i eth0 -f "host ucondb.example.com"

# Measure transfer rate
time curl -o /dev/null https://ucondb.example.com:9443/test_file
```

**Optimize Transfer Size:**

Blob size depends on run complexity. Typical range: 10-100 MB per run.

For slow networks:
```yaml
app:
    parallel_workers: 2  # Reduce concurrent transfers
    batch_size: 5        # Process fewer runs per execution
```

#### Latency Optimization

**Measure Round-Trip Time:**
```bash
# Ping test
ping -c 100 ucondb.example.com | tail -3

# HTTP latency
time curl -I https://ucondb.example.com:9443/instance/app
```

**Optimize for High Latency:**
```yaml
app:
    parallel_workers: 8  # More parallelism to compensate for latency
ucon_db:
    timeout_seconds: 120  # Allow longer for high-latency networks
```

#### DNS Resolution

**Cache DNS:**
```bash
# Install local DNS cache
sudo apt install nscd
sudo systemctl enable nscd
sudo systemctl start nscd
```

**Use IP Address (if DNS issues):**
```yaml
ucon_db:
    server_url: "https://192.168.1.100:9443/instance/app"
```

---

### CLI Tools vs API

**Performance Comparison:**

| Aspect | CLI Tools (bulkloader) | Python API (conftoolp) |
|--------|------------------------|------------------------|
| **Parallelism** | Yes (multi-process) | No (thread-unsafe) |
| **Speed** | ~5x faster | Baseline |
| **Memory** | Higher | Lower |
| **Setup** | Requires SSH (if remote) | Built-in |
| **Best For** | Large batches | Small batches, testing |

#### Using CLI Tools

**Configuration:**
```yaml
artdaq_db:
    use_tools: true
    remote_host: "artdaq-server.example.com"  # Optional: run on remote host
```

**Requirements:**
- SSH access to remote host (if `remote_host` specified)
- `bulkloader` and `bulkdownloader` in PATH
- Shared filesystem or tar-pipe transfer

**Benchmark:**
```bash
# Test with API
sed -i 's/use_tools: true/use_tools: false/' config.yaml
time ./run_archiver.sh config.yaml --import-only --incremental

# Test with CLI tools
sed -i 's/use_tools: false/use_tools: true/' config.yaml
time ./run_archiver.sh config.yaml --import-only --incremental
```

**Recommendation:** Use CLI tools for production with `parallel_workers > 2`.

---

## Log Analysis

### Reading Archiver Logs

#### Log Structure

**Format:**
```
TIMESTAMP - MODULE - LEVEL - MESSAGE
```

**Example:**
```
2025-10-24 14:32:15,123 - run_record_archiver.importer - INFO - Import Stage: Found 25 runs to import.
2025-10-24 14:32:16,456 - run_record_archiver.importer - INFO - → Processing run 12500 (attempt 1/3)
2025-10-24 14:32:18,789 - run_record_archiver.importer - INFO - ✓ Run 12500 imported successfully
```

#### Log Levels

- **DEBUG:** Detailed diagnostic information (use `-v` flag)
- **INFO:** Normal operational messages
- **WARNING:** Unexpected but recoverable conditions
- **ERROR:** Errors requiring attention
- **CRITICAL:** Severe errors requiring immediate action

---

### Identifying Patterns

#### Pattern: Transient Network Errors

**Log Signature:**
```
ERROR: Failed to upload blob for run 12500: Connection reset by peer
Retrying run 12500 in 3 seconds...
✓ Run 12500 migrated successfully
```

**Interpretation:** Network instability, but retries succeed.

**Action:** Monitor frequency. If > 10% of runs retry, investigate network.

#### Pattern: Persistent Database Errors

**Log Signature:**
```
ERROR: Run 12500 failed (attempt 1/3): ArtdaqDBError: Connection refused
ERROR: Run 12500 failed (attempt 2/3): ArtdaqDBError: Connection refused
ERROR: Run 12500 failed (attempt 3/3): ArtdaqDBError: Connection refused
✗ Run 12500 import failed
```

**Interpretation:** Database unreachable.

**Action:** Check database availability and connectivity.

#### Pattern: Permission Errors

**Log Signature:**
```
ERROR: Run 12500 failed: ArchiverError: Cannot read run records directory
Context: {'directory': '/daq/run_records/12500'}
```

**Interpretation:** Insufficient permissions.

**Action:** Verify archiver user has read access to `/daq/run_records`.

#### Pattern: Slow Processing

**Log Signature:**
```
INFO: Import Stage completed in 2456 seconds
INFO: Progress: 10/100 runs processed (10 successful, 0 failed)
INFO: Progress: 20/100 runs processed (20 successful, 0 failed)
...
```

**Interpretation:** Performance degradation (baseline: ~600 seconds).

**Action:** Check database performance, network latency, and system resources.

---

### Debug Mode Usage

**Enable Debug Logging:**

```bash
# Command-line flag (temporary)
./run_archiver.sh config.yaml --incremental -v

# Configuration file (persistent)
vim config.yaml
# Set: log_level: "DEBUG"
```

**Debug Output Includes:**
- Configuration expansion details
- Database query parameters and responses
- Network request/response headers
- File operations (reads, writes, deletes)
- State transitions
- Exception context and stack traces

**Example Debug Output:**
```
DEBUG - Reading state file: /var/lib/run_record_archiver/importer_state.json
DEBUG - State: {'last_contiguous_run': 12450, 'last_attempted_run': 12475}
DEBUG - Incremental start run: 12475
DEBUG - Querying ArtdaqDB: get_configurations()
DEBUG - ArtdaqDB response: {'success': True, 'configurations': [...]}
DEBUG - Found 25 candidate runs: [12476, 12477, ..., 12500]
DEBUG - Run 12500: Preparing FHiCL files for archive
DEBUG - Run 12500: Created temporary directory: /tmp/importer_12500_abc123
DEBUG - Run 12500: Copying boot.fcl -> /tmp/importer_12500_abc123/
DEBUG - Run 12500: Archiving to ArtdaqDB (initial insert)
DEBUG - ArtdaqDB: add_configuration(name='12500/BootDAQ', ...)
DEBUG - ArtdaqDB response: {'success': True, 'message': 'Configuration added'}
```

**Best Practice:** Only use debug mode for troubleshooting. It generates large log volumes.

---

### Log Rotation Management

#### Automatic Rotation

The archiver uses `SizeAndTimeRotatingFileHandler` with default settings:

- **Max size:** 500 MB per file
- **Max age:** 30 days
- **Backup count:** 5 files

**Configuration:**

These values are defined in `run_record_archiver/constants.py`:
```python
LOG_FILE_MAX_BYTES = 500 * 1024 * 1024  # 500 MB
LOG_FILE_MAX_AGE_SECONDS = 30 * 24 * 3600  # 30 days
LOG_FILE_BACKUP_COUNT = 5
```

**Rotation Behavior:**
- Rotates when file reaches 500 MB OR 30 days old
- Keeps 5 backup files: `archiver.log.1` through `archiver.log.5`
- Oldest backup deleted when new backup created

#### Manual Rotation

```bash
# Force rotation (if needed)
mv /var/lib/run_record_archiver/archiver.log \
   /var/lib/run_record_archiver/archiver.log.manual_$(date +%Y%m%d)

# Archiver will create new log file on next run
```

#### Disk Space Management

```bash
# Check log disk usage
du -sh /var/lib/run_record_archiver/*.log*

# Remove old backups (if needed)
find /var/lib/run_record_archiver -name "archiver.log.*" -mtime +60 -delete
```

#### External Log Management

**Ship to centralized logging:**
```bash
# Using rsyslog
# Add to /etc/rsyslog.d/archiver.conf:
$ModLoad imfile
$InputFileName /var/lib/run_record_archiver/archiver.log
$InputFileTag archiver:
$InputFileStateFile stat-archiver
$InputFileFacility local7
$InputRunFileMonitor
local7.* @logserver.example.com:514

# Restart rsyslog
sudo systemctl restart rsyslog
```

---

## Graceful Shutdown

### Normal Shutdown Procedure

**Interactive Execution:**

1. Press **Ctrl-C** once
2. Wait for current run to complete
3. Archiver saves state and exits

**Output:**
```
======================================================================
GRACEFUL SHUTDOWN REQUESTED (Ctrl-C)
Current run will finish processing...
Press Ctrl-C two more times within 2 seconds for immediate shutdown
======================================================================
Processing run 12500...
✓ Run 12500 imported successfully
Saving state...
======================================================================
✓ GRACEFUL SHUTDOWN COMPLETED
Reason: User interrupt
======================================================================
```

**Systemd Service:**

```bash
# Stop service (triggers SIGINT)
sudo systemctl stop run-record-archiver.service

# Monitor shutdown progress
sudo journalctl -u run-record-archiver.service -f
```

**Process Signal:**

```bash
# Send SIGINT to process
pkill -SIGINT -f run_record_archiver

# Or by PID
kill -SIGINT $(cat /var/lib/run_record_archiver/.archiver.lock)
```

---

### Immediate Shutdown

**When to Use:**
- Emergency situation requiring immediate stop
- Archiver stuck or unresponsive
- System maintenance requiring quick shutdown

**Procedure:**

Press **Ctrl-C** three times within 2 seconds:
```
Ctrl-C (1st press)
(< 2 seconds)
Ctrl-C (2nd press)
(< 2 seconds)
Ctrl-C (3rd press)
```

**Output:**
```
======================================================================
GRACEFUL SHUTDOWN REQUESTED (Ctrl-C)
...
======================================================================
Ctrl-C pressed 2/3 times - press 1 more for immediate shutdown
======================================================================
IMMEDIATE SHUTDOWN REQUESTED (3x Ctrl-C)
======================================================================
```

**Warning:** Immediate shutdown may leave:
- Current run in inconsistent state
- Lock file not cleaned up
- State not fully saved

**After Immediate Shutdown:**

```bash
# Remove stale lock
rm /var/lib/run_record_archiver/.archiver.lock

# Check state files
cat /var/lib/run_record_archiver/importer_state.json

# Resume with incremental mode
./run_archiver.sh config.yaml --incremental
```

---

### Verifying Shutdown Completion

```bash
# Check process list
ps aux | grep run_record_archiver
# Should return nothing

# Check lock file
ls -la /var/lib/run_record_archiver/.archiver.lock
# Should not exist

# Check last log entry
tail -5 /var/lib/run_record_archiver/archiver.log
# Should show "GRACEFUL SHUTDOWN COMPLETED" or "IMMEDIATE SHUTDOWN"

# Check state files were saved
ls -ltr /var/lib/run_record_archiver/*.json
# Timestamps should be recent
```

---

### Resuming After Shutdown

**Graceful Shutdown:**

State is automatically saved. Simply resume with incremental mode:
```bash
./run_archiver.sh config.yaml --incremental
```

**Immediate Shutdown or Crash:**

1. **Check State:**
```bash
cat /var/lib/run_record_archiver/importer_state.json
cat /var/lib/run_record_archiver/migrator_state.json
```

2. **Remove Lock:**
```bash
rm /var/lib/run_record_archiver/.archiver.lock
```

3. **Resume:**
```bash
# Resume with incremental mode
./run_archiver.sh config.yaml --incremental

# Or retry failures if needed
./run_archiver.sh config.yaml --retry-failed-import
./run_archiver.sh config.yaml --retry-failed-migrate
```

**Lock File Monitoring:**

The archiver includes automatic lock file monitoring. If the lock file is removed during execution (e.g., manual cleanup), it triggers graceful shutdown:

```
======================================================================
LOCK FILE REMOVED - INITIATING GRACEFUL SHUTDOWN
Lock file: /var/lib/run_record_archiver/.archiver.lock
Process will finish current run and then exit
======================================================================
```

**Best Practice:** Never manually remove the lock file while archiver is running. Use graceful shutdown instead.

---

## Emergency Procedures

### Stuck Processes

**Symptom:** Archiver process running for abnormally long time with no progress.

**Diagnosis:**
```bash
# Find process
ps aux | grep run_record_archiver

# Check CPU/memory usage
top -p $(pgrep -f run_record_archiver)

# Check what it's doing
strace -p $(pgrep -f run_record_archiver)

# Check recent log entries
tail -50 /var/lib/run_record_archiver/archiver.log
```

**Resolution:**

1. **Try Graceful Shutdown:**
```bash
pkill -SIGINT -f run_record_archiver
# Wait 5 minutes
```

2. **If Still Running, Force Kill:**
```bash
pkill -SIGKILL -f run_record_archiver
```

3. **Clean Up:**
```bash
# Remove lock file
rm /var/lib/run_record_archiver/.archiver.lock

# Check state files
cat /var/lib/run_record_archiver/importer_state.json
```

4. **Resume:**
```bash
./run_archiver.sh config.yaml --incremental
```

---

### Full Disk Recovery

**Symptom:**
```
OSError: [Errno 28] No space left on device
```

**Immediate Action:**

1. **Stop Archiver:**
```bash
pkill -SIGINT -f run_record_archiver
```

2. **Identify Space Hogs:**
```bash
# Check disk usage
df -h

# Find large files
du -h /var/lib/run_record_archiver | sort -hr | head -20

# Check log sizes
ls -lh /var/lib/run_record_archiver/*.log*
```

3. **Free Space:**

**Option A: Remove Old Log Backups**
```bash
# Remove logs older than 30 days
find /var/lib/run_record_archiver -name "*.log.*" -mtime +30 -delete

# Or remove all backups (keep current)
rm /var/lib/run_record_archiver/archiver.log.*
```

**Option B: Compress Logs**
```bash
# Compress old logs
gzip /var/lib/run_record_archiver/archiver.log.*
```

**Option C: Move Logs to Larger Partition**
```bash
# Move logs
mv /var/lib/run_record_archiver/*.log* /data/archiver_logs/

# Create symlink
ln -s /data/archiver_logs/archiver.log /var/lib/run_record_archiver/archiver.log
```

4. **Verify Space:**
```bash
df -h /var/lib/run_record_archiver
# Should have > 20% free
```

5. **Resume:**
```bash
./run_archiver.sh config.yaml --incremental
```

**Prevention:**
- Monitor disk space daily
- Set up alerts at 80% usage
- Configure log rotation aggressively
- Consider separate partition for logs

---

### Database Unavailability

**Symptom:**
```
ERROR: Failed to connect to database: Connection refused
ERROR: ArtdaqDBError: Cannot reach MongoDB server
ERROR: UconDBError: Failed to initialize UConDB client
```

**Diagnosis:**

**ArtdaqDB:**
```bash
# Test MongoDB connectivity
mongo --host mongodb-host --port 27017 --eval "db.version()"

# Test FilesystemDB access
ls -la /data/artdaqdb_archive
```

**UconDB:**
```bash
# Test HTTPS connectivity
curl -k https://ucondb.example.com:9443/instance/app

# Test authentication
curl -k -u username:password https://ucondb.example.com:9443/instance/app/folders
```

**Resolution:**

**Short-term (< 1 hour):**
- Wait for database to recover
- Archiver will automatically retry on next execution

**Medium-term (1-24 hours):**
- Run stages independently:
```bash
# If ArtdaqDB down, skip import
./run_archiver.sh config.yaml --migrate-only --incremental

# If UconDB down, run import only
./run_archiver.sh config.yaml --import-only --incremental
```

**Long-term (> 24 hours):**
- Disable scheduled execution
- Run manual catch-up after recovery:
```bash
# After database recovers
./run_archiver.sh config.yaml --incremental
./run_archiver.sh config.yaml --retry-failed-import
./run_archiver.sh config.yaml --retry-failed-migrate
```

**Post-Recovery:**
```bash
# Generate status report to verify state
./run_archiver.sh config.yaml --report-status --compare-state
```

---

### Network Outages

**Symptom:**
```
requests.exceptions.ConnectionError: Failed to establish connection
ERROR: Network is unreachable
ERROR: Read timed out
```

**Diagnosis:**
```bash
# Test basic connectivity
ping ucondb.example.com

# Test DNS resolution
nslookup ucondb.example.com

# Test routing
traceroute ucondb.example.com

# Test HTTPS
curl -I https://ucondb.example.com:9443
```

**Resolution:**

1. **Stop Archiver:**
```bash
pkill -SIGINT -f run_record_archiver
```

2. **Wait for Network Recovery**

3. **Resume After Recovery:**
```bash
# Clear any transient errors
./run_archiver.sh config.yaml --retry-failed-migrate

# Resume normal operation
./run_archiver.sh config.yaml --incremental
```

**Prevention:**
- Use `ucon_db.timeout_seconds` to handle transient issues
- Configure automatic retries in systemd:
```ini
[Service]
Restart=on-failure
RestartSec=300
```

---

### Crash Recovery

**Symptom:** Archiver terminated unexpectedly (no shutdown message in logs).

**Diagnosis:**
```bash
# Check system logs for crash reason
journalctl -xe | grep -i "archiver\|segfault\|killed"

# Check dmesg for OOM killer
dmesg | grep -i "out of memory\|killed process"

# Check last log entries
tail -100 /var/lib/run_record_archiver/archiver.log
```

**Common Crash Causes:**
- Out of memory (OOM killer)
- Segmentation fault (bug in conftoolp C extension)
- System reboot
- Power failure

**Recovery Steps:**

1. **Clean Up Lock:**
```bash
rm /var/lib/run_record_archiver/.archiver.lock
```

2. **Check State Files:**
```bash
# Verify JSON is valid
python3 -m json.tool /var/lib/run_record_archiver/importer_state.json
python3 -m json.tool /var/lib/run_record_archiver/migrator_state.json
```

3. **If State Corrupted, Recover:**
```bash
./run_archiver.sh config.yaml --recover-import-state
./run_archiver.sh config.yaml --recover-migrate-state
```

4. **Resume:**
```bash
./run_archiver.sh config.yaml --incremental
```

5. **Investigate Root Cause:**
```bash
# Review logs for patterns before crash
grep -B 20 "CRITICAL\|segfault" /var/lib/run_record_archiver/archiver.log
```

**Prevention:**
- Set memory limits in systemd service
- Monitor resource usage
- Report crashes to developers for bug fixes

---

## Routine Maintenance

### Log Management

**Daily:**
```bash
# Check log size
ls -lh /var/lib/run_record_archiver/archiver.log

# Check disk usage
df -h /var/lib/run_record_archiver
```

**Weekly:**
```bash
# Review old log backups
ls -lh /var/lib/run_record_archiver/archiver.log.*

# Compress old logs (optional)
gzip /var/lib/run_record_archiver/archiver.log.{3,4,5}
```

**Monthly:**
```bash
# Archive logs for long-term storage
tar -czf archiver_logs_$(date +%Y%m).tar.gz \
    /var/lib/run_record_archiver/*.log* \
    --remove-files --exclude=archiver.log

# Move archive to backup location
mv archiver_logs_*.tar.gz /backup/archiver/logs/
```

---

### State File Backup

**Automated Backup Script:**
```bash
#!/bin/bash
# backup_archiver_state.sh

BACKUP_DIR="/backup/archiver/state"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

tar -czf "$BACKUP_DIR/archiver_state_$TIMESTAMP.tar.gz" \
    /var/lib/run_record_archiver/*.json \
    /var/lib/run_record_archiver/*.log \
    ${HOME}/run_record_archiver/config.yaml

# Keep only last 30 days
find "$BACKUP_DIR" -name "archiver_state_*.tar.gz" -mtime +30 -delete

echo "Backup complete: archiver_state_$TIMESTAMP.tar.gz"
```

**Schedule via Cron:**
```bash
# Daily at 1 AM
0 1 * * * ${HOME}/run_record_archiver/backup_archiver_state.sh
```

---

### Failure Log Review

**Weekly Review:**
```bash
# Check failure counts
echo "Import failures: $(wc -l < /var/lib/run_record_archiver/import_failures.log)"
echo "Migration failures: $(wc -l < /var/lib/run_record_archiver/migrate_failures.log)"

# List failed runs
echo "Failed runs:"
sort -u /var/lib/run_record_archiver/import_failures.log /var/lib/run_record_archiver/migrate_failures.log
```

**Retry Failures:**
```bash
# Retry all failures
./run_archiver.sh config.yaml --retry-failed-import
./run_archiver.sh config.yaml --retry-failed-migrate

# Check if retries succeeded
echo "Remaining import failures: $(wc -l < /var/lib/run_record_archiver/import_failures.log)"
echo "Remaining migration failures: $(wc -l < /var/lib/run_record_archiver/migrate_failures.log)"
```

**Investigate Persistent Failures:**

```bash
# For runs that fail repeatedly, investigate individually
for run in $(cat /var/lib/run_record_archiver/import_failures.log); do
    echo "Investigating run $run..."
    ls -la /daq/run_records/$run
    # Check for:
    # - Missing files
    # - Permission issues
    # - Corrupted data
done
```

---

### Configuration Updates

**Safe Update Procedure:**

1. **Backup Current Configuration:**
```bash
cp config.yaml config.yaml.backup_$(date +%Y%m%d)
```

2. **Edit Configuration:**
```bash
vim config.yaml
```

3. **Validate Configuration:**
```bash
# Test configuration loading
python3 << 'EOF'
from run_record_archiver.config import Config
try:
    config = Config.from_file('config.yaml')
    print("✓ Configuration valid")
except Exception as e:
    print(f"✗ Configuration error: {e}")
    exit(1)
EOF
```

4. **Test with Status Report:**
```bash
./run_archiver.sh config.yaml --report-status
```

5. **Deploy:**
```bash
# If using systemd, reload service
sudo systemctl daemon-reload
sudo systemctl restart run-record-archiver.timer
```

**Common Configuration Updates:**

**Increase Parallelism:**
```yaml
# Before
app:
    parallel_workers: 2

# After
app:
    parallel_workers: 8
```

**Enable CLI Tools:**
```yaml
# Before
artdaq_db:
    use_tools: false

# After
artdaq_db:
    use_tools: true
```

**Adjust Logging:**
```yaml
# Before
app:
    log_level: "INFO"

# After (for debugging)
app:
    log_level: "DEBUG"
```

---

### Dependency Updates

**Check Current Versions:**
```bash
# Python version
python3 --version

# Package versions
pip list | grep -E "pyyaml|requests|psycopg2|ucondb|slack-bolt"
```

**Update Procedure:**

1. **Backup Virtual Environment:**
```bash
cp -r .venv .venv.backup_$(date +%Y%m%d)
```

2. **Update Packages:**
```bash
source .venv/bin/activate
pip install --upgrade pip
pip install --upgrade -r requirements.txt
```

3. **Test:**
```bash
./run_archiver.sh config.yaml --report-status
```

4. **If Issues, Rollback:**
```bash
rm -rf .venv
mv .venv.backup_YYYYMMDD .venv
```

**Note:** The bundled `conftoolp` and artdaq_database libraries should NOT be updated independently. They are version-locked to the archiver distribution.

---

## Capacity Planning

### Disk Space Requirements

**Work Directory:**
- State files: < 1 MB
- Lock file: < 1 KB
- Logs: 500 MB × 6 = 3 GB (current + 5 backups)
- **Total:** ~3.5 GB

**Temporary Directory:**
- Per run: 10-100 MB (during processing)
- Concurrent runs: `parallel_workers × max_run_size`
- **Estimate:** 2 GB for `parallel_workers: 8`, 50 MB average run size

**Total Recommended:**
- Minimum: 5 GB
- Recommended: 10 GB
- Production: 20 GB (allows for growth)

### Memory Requirements

**Per Process:**
- Base: 200 MB (Python, libraries)
- Per worker: 100-200 MB
- Per run: 50-100 MB (FHiCL processing)

**Formula:**
```
Memory = Base + (parallel_workers × worker_overhead) + (concurrent_runs × run_overhead)
Memory ≈ 200 + (workers × 150) + (workers × 75) MB
Memory ≈ 200 + (workers × 225) MB
```

**Examples:**
- 2 workers: 200 + (2 × 225) = 650 MB
- 4 workers: 200 + (4 × 225) = 1.1 GB
- 8 workers: 200 + (8 × 225) = 2.0 GB
- 16 workers: 200 + (16 × 225) = 3.8 GB

**Recommendation:** Allocate 2x calculated memory for safety margin.

### Network Bandwidth

**Upload Bandwidth:**
- Average blob size: 25 MB
- Upload time at various speeds:
  - 10 Mbps: 20 seconds
  - 100 Mbps: 2 seconds
  - 1 Gbps: 0.2 seconds

**Concurrent Uploads:**
- Bandwidth = `parallel_workers × average_blob_size / upload_time`
- Example: 8 workers × 25 MB / 2 sec = 100 MB/sec ≈ 800 Mbps

**Recommendation:**
- Minimum: 10 Mbps
- Recommended: 100 Mbps
- High-throughput: 1 Gbps

### Database Growth

**ArtdaqDB (FilesystemDB):**
- Per run: 5-50 MB (depends on configuration complexity)
- Annual growth: `runs_per_day × avg_size × 365`
- Example: 50 runs/day × 10 MB × 365 = 180 GB/year

**UconDB:**
- Per run: 10-100 MB (blob includes metadata)
- Managed by UconDB administrators

**Recommendation:** Plan for 200-500 GB per year of artdaqDB storage.

---

## Backup and Restore

### What to Backup

**Critical (must backup):**
- Configuration files: `config.yaml`, `archiver.env`
- State files: `*.json` in work directory
- Failure logs: `*_failures.log` in work directory

**Important (should backup):**
- Log files: `archiver.log*`
- Systemd service/timer files
- Cron configurations

**Not Necessary (can regenerate):**
- Virtual environment (`.venv/`)
- Lock files (`.archiver.lock`)
- Temporary files

### Backup Frequency

**Daily:**
- State files (automated)
- Failure logs (automated)

**Weekly:**
- Configuration files
- Full work directory

**Monthly:**
- Log archives
- Complete system snapshot

**Before Changes:**
- Always backup before configuration changes
- Always backup before upgrades

### Restore Procedures

#### Restore State Files

```bash
# Extract from backup
tar -xzf archiver_state_backup_YYYYMMDD.tar.gz -C /

# Verify
cat /var/lib/run_record_archiver/importer_state.json
cat /var/lib/run_record_archiver/migrator_state.json

# Test
./run_archiver.sh config.yaml --report-status
```

#### Restore Configuration

```bash
# Restore config
cp config.yaml.backup config.yaml

# Restore environment
cp archiver.env.backup archiver.env

# Validate
python3 -c "from run_record_archiver.config import Config; Config.from_file('config.yaml')"
```

#### Full System Restore

```bash
# 1. Restore application files
cd /opt
tar -xzf run_record_archiver_dist.tar.gz

# 2. Restore configuration
cp /backup/config.yaml ${HOME}/run_record_archiver/
cp /backup/archiver.env ${HOME}/run_record_archiver/

# 3. Restore work directory
tar -xzf /backup/archiver_state_latest.tar.gz -C /var/lib/

# 4. Restore systemd files
cp /backup/run-record-archiver.service /etc/systemd/system/
cp /backup/run-record-archiver.timer /etc/systemd/system/
sudo systemctl daemon-reload

# 5. Verify and resume
./run_archiver.sh config.yaml --report-status
sudo systemctl start run-record-archiver.timer
```

---

## Summary

This operations manual provides comprehensive guidance for running the Run Record Archiver in production. Key takeaways:

**Daily Operations:**
- Monitor execution status and failure counts
- Review logs for errors and patterns
- Verify disk space and resource usage

**Performance:**
- Tune `parallel_workers` based on system resources
- Use CLI tools for high-throughput scenarios
- Monitor and optimize database performance

**Reliability:**
- Use incremental mode for scheduled runs
- Implement automated backups
- Set up appropriate alerting

**Troubleshooting:**
- Use status reports to diagnose issues
- Leverage debug logging for investigation
- Follow state recovery procedures when needed

**For detailed procedures, see related documentation:**
- [Deployment Guide](DEPLOYMENT_GUIDE.md)
- [Troubleshooting Guide](TROUBLESHOOTING_GUIDE.md)
- [State Management Guide](STATE_MANAGEMENT_GUIDE.md)

**Last Updated:** 2025-10-24
