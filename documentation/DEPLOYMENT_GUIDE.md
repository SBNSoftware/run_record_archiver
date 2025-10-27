# Deployment Guide - Run Record Archiver

## Table of Contents

- [Overview](#overview)
- [System Requirements](#system-requirements)
- [Pre-Deployment Checklist](#pre-deployment-checklist)
- [Deployment Methods](#deployment-methods)
  - [Method 1: Distribution Package (Recommended)](#method-1-distribution-package-recommended)
  - [Method 2: From Source (Development)](#method-2-from-source-development)
- [Configuration](#configuration)
- [Environment Setup](#environment-setup)
- [Verification](#verification)
- [Integration with Schedulers](#integration-with-schedulers)
- [Multi-Instance Deployment](#multi-instance-deployment)
- [Upgrade Procedures](#upgrade-procedures)
- [Rollback Procedures](#rollback-procedures)
- [Security Hardening](#security-hardening)
- [Troubleshooting Deployment](#troubleshooting-deployment)

---

## Overview

This guide provides step-by-step instructions for deploying the Run Record Archiver in production environments. The archiver is distributed as a self-contained package with all dependencies bundled, enabling deployment on systems without the full artdaq_database software stack.

**Distribution Package Characteristics:**
- Self-contained with all dependencies (172 MB)
- No external artdaq_database setup required
- Portable across compatible Linux distributions
- Includes convenience scripts for automatic setup
- Production-ready configuration templates

---

## System Requirements

### Operating System
- **Supported**: RHEL/CentOS/AlmaLinux 8+, Ubuntu 20.04+, Debian 11+
- **Architecture**: x86_64 (64-bit)
- **Kernel**: Linux 4.x or higher

### Software Requirements
- **Python**: 3.8, 3.9, 3.10, or 3.11
- **Bash**: 4.0 or higher (for launcher scripts)
- **Network**: Outbound HTTPS access to UconDB server
- **Optional**: SSH client (if using remote CLI tools mode)

### Hardware Requirements

**Minimum:**
- CPU: 2 cores
- RAM: 2 GB
- Disk: 500 MB for application + space for logs and state files

**Recommended:**
- CPU: 4+ cores (for concurrent processing)
- RAM: 4+ GB
- Disk: 10 GB (for logs, state files, and temporary data)
- Network: 100 Mbps+ for large run transfers

### Network Requirements

**Required Connections:**
- **ArtdaqDB**: Access to MongoDB server or FilesystemDB mount
- **UconDB**: HTTPS access to UconDB server (typically port 9443)
- **Source Filesystem**: Read access to run records directory

**Optional Connections:**
- **Email**: SMTP server access (port 25, 587, or 465)
- **Slack**: HTTPS access to slack.com API
- **Carbon/Graphite**: TCP access to Carbon server (typically port 2003)
- **SSH**: Access to remote host (if using remote CLI tools)

### File System Requirements

**Disk Space:**
- Application: 500 MB (distribution package)
- State files: < 1 MB
- Log files: 500 MB per log file × 5 backups = 2.5 GB (configurable)
- Temporary data: Varies by run size (typically 10-100 MB per run)

**Permissions:**
- Read access to source run records directory
- Write access to work directory
- Write access to log directory
- Read/write access to artdaqDB (if FilesystemDB)

---

## Pre-Deployment Checklist

Before deploying, ensure you have:

- [ ] Compatible Linux system with Python 3.8+
- [ ] Network access to all required services (artdaqDB, UconDB)
- [ ] Credentials for UconDB writer access
- [ ] Access to source run records directory
- [ ] Dedicated work directory with write permissions
- [ ] Distribution package (run_record_archiver_dist.tar.gz or similar)
- [ ] Configuration values (database URIs, paths, credentials)
- [ ] (Optional) SMTP server details for email notifications
- [ ] (Optional) Slack bot token for Slack notifications
- [ ] Deployment plan (scheduled vs on-demand execution)

---

## Deployment Methods

### Method 1: Distribution Package (Recommended)

This is the recommended method for production deployments.

#### Step 1: Extract Distribution Package

```bash
# Create installation directory
sudo mkdir -p ${HOME}/run_record_archiver
cd ${HOME}/run_record_archiver

# Extract distribution package
tar -xzf /path/to/run_record_archiver_dist.tar.gz
# OR if extracted to 'dist' directory:
# cp -r /path/to/dist/* .

# Verify extraction
ls -la
# Should show: config.yaml.template, requirements.txt, run_archiver.sh,
#              run_record_archiver/, tools/, lib/
```

#### Step 2: Set Directory Permissions

```bash
# Set ownership (adjust user/group as needed)
sudo chown -R archiver:archiver ${HOME}/run_record_archiver

# Set permissions
sudo chmod 755 ${HOME}/run_record_archiver
sudo chmod 755 ${HOME}/run_record_archiver/run_archiver.sh
sudo chmod 644 ${HOME}/run_record_archiver/config.yaml.template
sudo chmod -R 755 ${HOME}/run_record_archiver/lib
```

#### Step 3: Create Work Directory

```bash
# Create work directory for state files, logs, etc.
sudo mkdir -p /var/lib/run_record_archiver
sudo chown archiver:archiver /var/lib/run_record_archiver
sudo chmod 755 /var/lib/run_record_archiver
```

#### Step 4: Create Configuration File

```bash
# Copy template
cd ${HOME}/run_record_archiver
cp config.yaml.template config.yaml

# Edit configuration (see Configuration section below)
vim config.yaml
# OR use your preferred editor
```

#### Step 5: Create Environment File

The `run_archiver.sh` script automatically loads environment variables from `archiver.env` if present.

```bash
# Create environment file
cat > archiver.env << 'EOF'
# Work directory for state files and logs
WORK_DIR=/var/lib/run_record_archiver

# Source filesystem path
RUN_RECORDS_DIR=/daq/run_records

# ArtdaqDB connection
ARTDAQDB_URL=filesystemdb:///path/to/artdaqdb_archive

# UconDB connection
UCONDB_URL=https://ucondb.example.com:9443/myexp_on_ucon_prod/app
UCONDB_USER=archiver_service
UCONDB_PASSWORD=your_secure_password

# Notification settings (optional)
NOTIFY_EMAIL_LIST=team@example.com

# Metrics settings (optional)
EXPERIMENT_NAME=myexp
EOF

# Secure the file (contains passwords)
chmod 600 archiver.env
chown archiver:archiver archiver.env
```

#### Step 6: Initialize Virtual Environment

```bash
# Initialize Python virtual environment and install dependencies
./run_archiver.sh --init-venv --help

# This will:
# 1. Create .venv/ directory
# 2. Install Python dependencies
# 3. Set up environment variables
# 4. Display help message
```

#### Step 7: Test Deployment

```bash
# Test configuration
./run_archiver.sh config.yaml --report-status

# Expected: Status report showing runs in filesystem, artdaqDB, and UconDB
```

**Deployment Complete!** Proceed to [Verification](#verification) section.

---

### Method 2: From Source (Development)

Use this method for development or when you need to modify the code.

#### Step 1: Clone Repository

```bash
# Clone repository
git clone https://github.com/your-org/run_record_archiver.git
cd run_record_archiver
```

#### Step 2: Set Up Environment

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Set environment variables
export PYTHONPATH="${PWD}/lib:${PYTHONPATH}"
export LD_LIBRARY_PATH="${PWD}/lib:${LD_LIBRARY_PATH}"
export PATH="${PWD}/lib:${PATH}"

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

#### Step 3: Configure

```bash
# Create configuration file from template
cp config.yaml.template config.yaml
vim config.yaml
```

#### Step 4: Run

```bash
# Run directly
python -m run_record_archiver config.yaml --report-status
```

**Note:** For production deployment from source, use the `tools/create-dist` utility to create a distribution package, then follow Method 1.

---

## Configuration

### Configuration File Structure

The `config.yaml` file contains all runtime configuration. See the template for detailed comments.

**Key Configuration Sections:**

1. **app**: Application settings (work directory, logging, parallelism)
2. **fhiclize_generate**: FHiCL file processing options
3. **source_files**: Source filesystem paths
4. **artdaq_db**: ArtdaqDB connection and settings
5. **ucon_db**: UconDB connection and authentication
6. **reporting**: Email and Slack notification settings
7. **carbon**: Optional metrics reporting

### Minimal Production Configuration

```yaml
app:
    work_dir: "/var/lib/run_record_archiver"
    batch_size: 10
    parallel_workers: 2
    log_level: "INFO"
    log_file: "${work_dir}/archiver.log"

fhiclize_generate:
    - boot
    - metadata
    - known_boardreaders_list
    - RunHistory
    - settings

source_files:
    run_records_dir: "/daq/run_records"

artdaq_db:
    fcl_conf_dir: "${HOME}/artdaq_database/conf"
    database_uri: "filesystemdb:///data/artdaqdb_archive"
    use_tools: false

ucon_db:
    server_url: "https://ucondb.example.com:9443/instance/app"
    folder_name: "production"
    object_name: "configuration"
    timeout_seconds: 10
    writer_user: "archiver_service"
    writer_password: "${UCONDB_PASSWORD}"

reporting:
    email:
        enabled: false
    slack:
        enabled: false

carbon:
    enabled: false
```

### Environment Variable Expansion

Configuration values support environment variable expansion:

```yaml
# Simple substitution
work_dir: "${WORK_DIR}"

# With default value
work_dir: "${WORK_DIR:-/tmp/archiver}"

# Parameter reference (same section)
log_file: "${work_dir}/archiver.log"

# Cross-section reference
some_path: "${app.work_dir}/data"
```

### Security Considerations

**Sensitive Data:**
- Store passwords in environment variables, not in config.yaml
- Use `archiver.env` file with restrictive permissions (600)
- Use secure credential management (e.g., HashiCorp Vault) for production

**Example secure configuration:**

```yaml
ucon_db:
    writer_user: "${UCONDB_USER}"
    writer_password: "${UCONDB_PASSWORD}"

reporting:
    email:
        smtp_password: "${SMTP_PASSWORD}"
    slack:
        bot_token: "${SLACK_BOT_TOKEN}"
```

---

## Environment Setup

### Environment Variables

The `run_archiver.sh` script handles environment setup automatically, but you can also set these manually:

```bash
# Required for Python to find conftoolp module
export PYTHONPATH="${HOME}/run_record_archiver/lib:${PYTHONPATH}"

# Required for shared library resolution
export LD_LIBRARY_PATH="${HOME}/run_record_archiver/lib:${LD_LIBRARY_PATH}"

# Required for CLI tools (bulkloader, bulkdownloader, etc.)
export PATH="${HOME}/run_record_archiver/lib:${PATH}"

# Locale settings (prevents encoding issues)
export LANG=en_US.UTF-8
export LANGUAGE=en_US.UTF-8
export LC_ALL=en_US.UTF-8
```

### Launcher Script Options

The `run_archiver.sh` script supports these special flags:

```bash
# Initialize or recreate virtual environment
./run_archiver.sh --init-venv

# Quiet mode (suppress setup output)
./run_archiver.sh --quiet config.yaml

# Combined
./run_archiver.sh --init-venv --quiet
```

**Default behavior:**
- Creates `.venv/` if it doesn't exist
- Loads `archiver.env` if present
- Sets PYTHONPATH, LD_LIBRARY_PATH, PATH
- Uses `config.yaml` as default config file if not specified

---

## Verification

### Smoke Tests

#### Test 1: Configuration Validation

```bash
# Should display help message without errors
./run_archiver.sh --help
```

#### Test 2: Environment Check

```bash
# Verify Python can import all modules
./run_archiver.sh -c "
from run_record_archiver.config import Config
from run_record_archiver.clients.artdaq import ArtdaqDBClient
from run_record_archiver.clients.ucondb import UconDBClient
print('All imports successful')
"
```

#### Test 3: Configuration Loading

```bash
# Should load configuration without errors
python3 << 'EOF'
from run_record_archiver.config import Config
config = Config.from_file('config.yaml')
print(f'Work dir: {config.app.work_dir}')
print(f'Log level: {config.app.log_level}')
print('Configuration loaded successfully')
EOF
```

#### Test 4: Status Report

```bash
# Generate status report (read-only operation)
./run_archiver.sh config.yaml --report-status

# Expected output:
# - Filesystem scan results
# - ArtdaqDB query results
# - UconDB query results
# - Comparison and gap analysis
```

#### Test 5: Database Connectivity

```bash
# Test ArtdaqDB connection
python3 << 'EOF'
from run_record_archiver.config import Config
from run_record_archiver.clients.artdaq import ArtdaqDBClient

config = Config.from_file('config.yaml')
client = ArtdaqDBClient(
    database_uri=config.artdaq_db.database_uri,
    fcl_conf_dir=config.artdaq_db.fcl_conf_dir,
    use_tools=config.artdaq_db.use_tools,
    remote_host=config.artdaq_db.remote_host
)
runs = client.list_runs(limit=10)
print(f'ArtdaqDB: Found {len(runs)} runs')
EOF
```

```bash
# Test UconDB connection
python3 << 'EOF'
from run_record_archiver.config import Config
from run_record_archiver.clients.ucondb import UconDBClient

config = Config.from_file('config.yaml')
client = UconDBClient(
    server_url=config.ucon_db.server_url,
    folder_name=config.ucon_db.folder_name,
    object_name=config.ucon_db.object_name,
    writer_user=config.ucon_db.writer_user,
    writer_password=config.ucon_db.writer_password,
    timeout_seconds=config.ucon_db.timeout_seconds
)
runs = client.list_runs(limit=10)
print(f'UconDB: Found {len(runs)} runs')
EOF
```

### Expected Results

All smoke tests should complete without errors. If any test fails:

1. Check error messages for specific issues
2. Verify configuration values
3. Verify network connectivity
4. Check credentials
5. Review logs for details

---

## Integration with Schedulers

### Systemd Timer (Recommended)

Create a systemd service and timer for periodic execution.

#### Service File: `/etc/systemd/system/run-record-archiver.service`

```ini
[Unit]
Description=Run Record Archiver
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=archiver
Group=archiver
WorkingDirectory=${HOME}/run_record_archiver
ExecStart=${HOME}/run_record_archiver/run_archiver.sh config.yaml --incremental
StandardOutput=journal
StandardError=journal
SyslogIdentifier=run-record-archiver

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/run_record_archiver
ReadOnlyPaths=/daq/run_records

# Resource limits
MemoryMax=4G
CPUQuota=200%

[Install]
WantedBy=multi-user.target
```

#### Timer File: `/etc/systemd/system/run-record-archiver.timer`

```ini
[Unit]
Description=Run Record Archiver Timer
Requires=run-record-archiver.service

[Timer]
# Run every hour
OnCalendar=hourly
# Run immediately if missed
Persistent=true
# Random delay to avoid thundering herd
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
```

#### Enable and Start

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable timer (start on boot)
sudo systemctl enable run-record-archiver.timer

# Start timer
sudo systemctl start run-record-archiver.timer

# Check status
sudo systemctl status run-record-archiver.timer
sudo systemctl list-timers run-record-archiver.timer

# View logs
sudo journalctl -u run-record-archiver.service -f
```

### Cron (Alternative)

Add to `/etc/cron.d/run-record-archiver`:

```cron
# Run every hour at 5 minutes past the hour
5 * * * * archiver ${HOME}/run_record_archiver/run_archiver.sh ${HOME}/run_record_archiver/config.yaml --incremental >> /var/log/run-record-archiver-cron.log 2>&1

# Run full status report daily at 6 AM
0 6 * * * archiver ${HOME}/run_record_archiver/run_archiver.sh ${HOME}/run_record_archiver/config.yaml --report-status >> /var/log/run-record-archiver-report.log 2>&1
```

**Permissions:**

```bash
sudo chmod 644 /etc/cron.d/run-record-archiver
sudo touch /var/log/run-record-archiver-cron.log
sudo chown archiver:archiver /var/log/run-record-archiver-cron.log
```

### Manual Execution

For on-demand execution:

```bash
# Full pipeline (both stages)
./run_archiver.sh config.yaml

# Incremental mode (only new runs)
./run_archiver.sh config.yaml --incremental

# Import stage only
./run_archiver.sh config.yaml --import-only --incremental

# Migration stage only
./run_archiver.sh config.yaml --migrate-only --incremental
```

---

## Multi-Instance Deployment

### Scenario: Multiple Experiments

Deploy separate instances for different experiments:

```bash
# Instance 1: SBND
${HOME}/run_record_archiver_myexp/
    config.yaml  # Points to SBND databases
    archiver.env # SBND-specific variables

# Instance 2: ICARUS
${HOME}/run_record_archiver_icarus/
    config.yaml  # Points to ICARUS databases
    archiver.env # ICARUS-specific variables
```

Each instance has:
- Separate work directory
- Separate configuration
- Separate lock file (prevents concurrent execution)
- Can run simultaneously (different experiments)

### Scenario: Separate Import and Migration

Run import and migration as separate processes:

```systemd
# Service 1: Import only
ExecStart=${HOME}/run_record_archiver/run_archiver.sh config.yaml --import-only --incremental

# Service 2: Migration only (runs after import)
ExecStart=${HOME}/run_record_archiver/run_archiver.sh config.yaml --migrate-only --incremental
```

**Important:** Use the same work directory for both services to share state files.

### File Locking

The archiver uses file locking to prevent concurrent execution:

- Lock file: Specified in `app.lock_file` configuration
- Behavior: Exits with error if lock exists
- Cleanup: Automatic on normal exit, manual cleanup may be needed after crashes

---

## Upgrade Procedures

### Upgrade from Previous Version

#### Step 1: Backup Current Installation

```bash
# Backup current version
sudo cp -r ${HOME}/run_record_archiver ${HOME}/run_record_archiver.backup

# Backup configuration and state
sudo tar -czf ${HOME}/archiver-state-backup-$(date +%Y%m%d).tar.gz \
    ${HOME}/run_record_archiver/config.yaml \
    ${HOME}/run_record_archiver/archiver.env \
    /var/lib/run_record_archiver/
```

#### Step 2: Stop Running Services

```bash
# If using systemd timer
sudo systemctl stop run-record-archiver.timer
sudo systemctl stop run-record-archiver.service

# Verify no archiver processes running
ps aux | grep run_record_archiver
```

#### Step 3: Extract New Version

```bash
# Extract new version to temporary location
cd /tmp
tar -xzf run_record_archiver_dist_v2.0.tar.gz

# Backup and replace application files
sudo mv ${HOME}/run_record_archiver/run_record_archiver ${HOME}/run_record_archiver/run_record_archiver.old
sudo mv ${HOME}/run_record_archiver/lib ${HOME}/run_record_archiver/lib.old
sudo mv ${HOME}/run_record_archiver/tools ${HOME}/run_record_archiver/tools.old

sudo cp -r /tmp/dist/run_record_archiver ${HOME}/run_record_archiver/
sudo cp -r /tmp/dist/lib ${HOME}/run_record_archiver/
sudo cp -r /tmp/dist/tools ${HOME}/run_record_archiver/
sudo cp /tmp/dist/run_archiver.sh ${HOME}/run_record_archiver/
sudo cp /tmp/dist/requirements.txt ${HOME}/run_record_archiver/
```

#### Step 4: Update Configuration

```bash
# Compare configurations
diff ${HOME}/run_record_archiver/config.yaml /tmp/dist/config.yaml.template

# Update config.yaml if new parameters added
vim ${HOME}/run_record_archiver/config.yaml
```

#### Step 5: Reinstall Virtual Environment

```bash
cd ${HOME}/run_record_archiver
./run_archiver.sh --init-venv --help
```

#### Step 6: Verify Upgrade

```bash
# Test configuration
./run_archiver.sh config.yaml --report-status

# Check logs for any issues
tail -f /var/lib/run_record_archiver/archiver.log
```

#### Step 7: Restart Services

```bash
# If using systemd
sudo systemctl start run-record-archiver.timer
sudo systemctl status run-record-archiver.timer
```

---

## Rollback Procedures

### Rollback to Previous Version

If upgrade fails:

#### Step 1: Stop Services

```bash
sudo systemctl stop run-record-archiver.timer
sudo systemctl stop run-record-archiver.service
```

#### Step 2: Restore Previous Version

```bash
# Remove new version
sudo rm -rf ${HOME}/run_record_archiver/run_record_archiver
sudo rm -rf ${HOME}/run_record_archiver/lib
sudo rm -rf ${HOME}/run_record_archiver/tools

# Restore backup
sudo mv ${HOME}/run_record_archiver/run_record_archiver.old ${HOME}/run_record_archiver/run_record_archiver
sudo mv ${HOME}/run_record_archiver/lib.old ${HOME}/run_record_archiver/lib
sudo mv ${HOME}/run_record_archiver/tools.old ${HOME}/run_record_archiver/tools
```

#### Step 3: Restore State Files (if needed)

```bash
# Only if state files were corrupted
sudo tar -xzf ${HOME}/archiver-state-backup-YYYYMMDD.tar.gz -C /
```

#### Step 4: Restart Services

```bash
sudo systemctl start run-record-archiver.timer
sudo systemctl status run-record-archiver.timer
```

---

## Security Hardening

### File Permissions

```bash
# Application directory: read-only for archiver user
sudo chown -R root:archiver ${HOME}/run_record_archiver
sudo chmod -R 755 ${HOME}/run_record_archiver

# Configuration files: read-only
sudo chmod 644 ${HOME}/run_record_archiver/config.yaml

# Environment file: readable only by archiver user (contains passwords)
sudo chown archiver:archiver ${HOME}/run_record_archiver/archiver.env
sudo chmod 600 ${HOME}/run_record_archiver/archiver.env

# Work directory: read-write for archiver user
sudo chown -R archiver:archiver /var/lib/run_record_archiver
sudo chmod 755 /var/lib/run_record_archiver
```

### Network Security

**Firewall Rules:**

```bash
# Allow outbound HTTPS to UconDB
sudo firewall-cmd --permanent --add-rich-rule='
  rule family="ipv4"
  destination address="ucondb.example.com"
  port port="9443" protocol="tcp"
  accept'

# Reload firewall
sudo firewall-cmd --reload
```

### Credential Management

**Best Practices:**

1. **Never commit credentials to version control**
2. **Use environment variables** for all secrets
3. **Restrict file permissions** on archiver.env (600)
4. **Rotate credentials** regularly
5. **Use service accounts** with minimal permissions
6. **Enable audit logging** for credential access

**Example using HashiCorp Vault:**

```bash
# Fetch credentials from Vault
export UCONDB_PASSWORD=$(vault kv get -field=password secret/archiver/ucondb)
export SLACK_BOT_TOKEN=$(vault kv get -field=token secret/archiver/slack)

# Run archiver
./run_archiver.sh config.yaml
```

### SELinux Configuration

If using SELinux:

```bash
# Set context for application directory
sudo semanage fcontext -a -t bin_t "${HOME}/run_record_archiver(/.*)?"
sudo restorecon -R ${HOME}/run_record_archiver

# Set context for work directory
sudo semanage fcontext -a -t var_lib_t "/var/lib/run_record_archiver(/.*)?"
sudo restorecon -R /var/lib/run_record_archiver
```

---

## Troubleshooting Deployment

### Issue: Python Module Import Errors

**Symptom:**
```
ModuleNotFoundError: No module named 'conftoolp'
```

**Solution:**
```bash
# Verify PYTHONPATH includes lib directory
echo $PYTHONPATH
# Should contain: ${HOME}/run_record_archiver/lib

# If using run_archiver.sh, it sets this automatically
# If running manually, set explicitly:
export PYTHONPATH="${HOME}/run_record_archiver/lib:${PYTHONPATH}"
```

### Issue: Shared Library Not Found

**Symptom:**
```
ImportError: libartdaq-database_ConfigurationDB.so: cannot open shared object file
```

**Solution:**
```bash
# Verify LD_LIBRARY_PATH includes lib directory
echo $LD_LIBRARY_PATH
# Should contain: ${HOME}/run_record_archiver/lib

# Set explicitly:
export LD_LIBRARY_PATH="${HOME}/run_record_archiver/lib:${LD_LIBRARY_PATH}"
```

### Issue: Permission Denied

**Symptom:**
```
PermissionError: [Errno 13] Permission denied: '/var/lib/run_record_archiver/archiver.log'
```

**Solution:**
```bash
# Check ownership
ls -la /var/lib/run_record_archiver

# Fix ownership
sudo chown -R archiver:archiver /var/lib/run_record_archiver
```

### Issue: Lock File Exists

**Symptom:**
```
LockExistsError: Lock file exists: /var/lib/run_record_archiver/.archiver.lock
```

**Solution:**
```bash
# Check if archiver is actually running
ps aux | grep run_record_archiver

# If not running, remove lock file
rm /var/lib/run_record_archiver/.archiver.lock

# If running, wait for completion or use graceful shutdown
pkill -SIGINT -f run_record_archiver
```

### Issue: Configuration Validation Errors

**Symptom:**
```
ArchiverError: Configuration validation failed
```

**Solution:**
```bash
# Validate YAML syntax
python3 -c "import yaml; yaml.safe_load(open('config.yaml'))"

# Check for required parameters
grep -E "work_dir|database_uri|server_url" config.yaml

# Verify environment variables are set
echo $WORK_DIR $ARTDAQDB_URL $UCONDB_URL
```

### Issue: Database Connection Failures

**Symptom:**
```
ArtdaqDBError: Failed to connect to database
```

**Solution:**
```bash
# Test network connectivity
ping -c 3 mongodb-host

# Test MongoDB connection (if using MongoDB)
mongo --host mongodb-host --port 27017 --eval "db.version()"

# Test FilesystemDB access (if using FilesystemDB)
ls -la /path/to/artdaqdb_archive

# Verify database URI format in config.yaml
```

For additional troubleshooting, see [TROUBLESHOOTING_GUIDE.md](TROUBLESHOOTING_GUIDE.md).

---

## Next Steps

After successful deployment:

1. **Configure Monitoring**: Set up monitoring for logs and metrics
2. **Test Failure Scenarios**: Test retry and recovery procedures
3. **Schedule Regular Runs**: Set up systemd timer or cron
4. **Configure Notifications**: Enable email or Slack alerts
5. **Document Custom Settings**: Keep notes on environment-specific configuration
6. **Plan Maintenance Windows**: Schedule regular reviews and updates

---

**Related Documentation:**
- [Configuration Guide](../run_record_archiver/config.md) - Detailed configuration reference
- [Operations Manual](OPERATIONS_MANUAL.md) - Daily operational procedures
- [Troubleshooting Guide](TROUBLESHOOTING_GUIDE.md) - Common issues and solutions
- [State Management Guide](STATE_MANAGEMENT_GUIDE.md) - State recovery procedures

**Last Updated:** 2025-10-24
