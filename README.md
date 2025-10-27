# Run Record Archiver

A Python-based utility for archiving artdaq run record configurations through a robust two-stage pipeline, providing reliable migration from filesystem sources to intermediate artdaqDB storage and final archival in UconDB.

## Overview

The Run Record Archiver automates the process of collecting, transforming, and archiving run records from particle physics data acquisition systems. It provides:

- **Two-Stage Pipeline**: Import stage (filesystem → artdaqDB) and Migration stage (artdaqDB → UconDB)
- **Robust Failure Handling**: Automatic retries, failure tracking, and recovery mechanisms
- **Concurrent Processing**: Parallel batch processing with configurable worker pools
- **State Management**: Incremental mode with contiguous run tracking to prevent gaps
- **Flexible Deployment**: Self-contained distribution with bundled dependencies (no full artdaq_database stack required)

## Quick Start

### Prerequisites

- Python 3.9+ (3.9, 3.10, or 3.11)
- Linux (RHEL/CentOS/AlmaLinux 9+)
- Network access to UconDB server

### Installation

```bash
# 1. Extract the distribution package
tar -xzf run_record_archiver-dist.tar.gz
cd dist

# 2. Create configuration from template
cp config.yaml.template config.yaml

# 3. Edit config.yaml to match your environment
# See documentation/DEPLOYMENT_GUIDE.md for details

# 4. Run the archiver
./run_archiver.sh config.yaml
```

### Basic Usage

```bash
# Full pipeline (import + migrate)
./run_archiver.sh config.yaml

# Incremental mode (process only new runs)
./run_archiver.sh config.yaml --incremental

# Import stage only
./run_archiver.sh config.yaml --import-only

# Migration stage only
./run_archiver.sh config.yaml --migrate-only

# Generate status report
./run_archiver.sh config.yaml --report-status

# Enable debug logging
./run_archiver.sh config.yaml -v
```

## Architecture

### Pipeline Stages

1. **Import Stage**: Scans filesystem for new run records, transforms configurations to FHiCL format, and imports into artdaqDB (MongoDB or FilesystemDB)

2. **Migration Stage**: Exports runs from artdaqDB, packages them into text blobs, and uploads to UconDB server with MD5 verification

### Key Features

- **Stateful Tracking**: Maintains last contiguous successful run number for incremental processing
- **Failure Recovery**: Logs failed runs and provides retry mechanisms
- **State Recovery**: Rebuilds state files from data sources (filesystem, artdaqDB, UconDB)
- **Concurrent Processing**: ThreadPoolExecutor with configurable parallelism
- **Graceful Shutdown**: Handles SIGINT/SIGTERM with in-progress task completion
- **Performance Options**: Choose between Python API or CLI tools for high-throughput operations

## Documentation

### Getting Started

- **[DEPLOYMENT_GUIDE.md](documentation/DEPLOYMENT_GUIDE.md)** - Complete deployment instructions, system requirements, and configuration
- **[OPERATIONS_MANUAL.md](documentation/OPERATIONS_MANUAL.md)** - Daily operations, monitoring, and execution patterns

### Configuration & Usage

- **[config.yaml.template](config.yaml.template)** - Configuration template with inline documentation
- **[FILE_FORMATS.md](documentation/FILE_FORMATS.md)** - State files, logs, and data format specifications

### Technical Reference

- **[CORE_MODULES.md](documentation/CORE_MODULES.md)** - Core module architecture and implementation details
- **[clients_README.md](documentation/clients_README.md)** - Database client implementations (ArtdaqDB, UconDB, Carbon)
- **[services_README.md](documentation/services_README.md)** - Service layer components (blob creation, FHiCL preparation, reporting)
- **[persistence_README.md](documentation/persistence_README.md)** - State management and file locking
- **[fhiclutils_README.md](documentation/fhiclutils_README.md)** - FHiCL conversion and validation utilities

### Operations & Maintenance

- **[STATE_MANAGEMENT_GUIDE.md](documentation/STATE_MANAGEMENT_GUIDE.md)** - State tracking, recovery, and incremental mode
- **[TROUBLESHOOTING_GUIDE.md](documentation/TROUBLESHOOTING_GUIDE.md)** - Common issues, debugging techniques, and solutions
- **[EXIT_CODES.md](documentation/EXIT_CODES.md)** - Complete exit code reference

## Project Structure

```
/
├── README.md                      # This file
├── config.yaml.template           # Configuration template
├── requirements.txt               # Python dependencies
├── run_archiver.sh               # Main launcher script
├── run_record_archiver/          # Main application package
│   ├── __main__.py               # CLI entry point
│   ├── orchestrator.py           # Pipeline orchestration
│   ├── importer.py               # Import stage implementation
│   ├── migrator.py               # Migration stage implementation
│   ├── reporter.py               # Status reporting
│   ├── config.py                 # Configuration management
│   ├── base_stage.py             # Abstract base for stages
│   ├── clients/                  # Database clients
│   │   ├── artdaq.py            # ArtdaqDB client
│   │   ├── ucondb.py            # UconDB client
│   │   └── carbon.py            # Metrics client
│   ├── services/                 # Service layer
│   │   ├── blob_creator.py      # Blob packaging
│   │   ├── fcl_preparer.py      # FHiCL transformation
│   │   ├── blob_validator.py    # Validation
│   │   └── reporting.py         # Notifications
│   ├── persistence/              # State management
│   │   ├── state.py             # State tracking
│   │   └── lock.py              # File locking
│   └── fhiclutils/              # FHiCL utilities
│       ├── converters.py        # Format converters
│       ├── validator.py         # Validation
│       └── utils.py             # Utilities
├── lib/                          # Bundled dependencies
│   ├── conftoolp.py             # Python wrapper
│   ├── _conftoolp.so            # C++ bindings
│   ├── bulkloader                # CLI import tool
│   ├── bulkdownloader            # CLI export tool
│   └── lib*.so                   # Shared libraries
├── tools/                        # Comparison and analysis tools
└── documentation/                # Detailed documentation
    ├── DEPLOYMENT_GUIDE.md
    ├── OPERATIONS_MANUAL.md
    ├── CORE_MODULES.md
    ├── clients_README.md
    ├── services_README.md
    ├── persistence_README.md
    ├── fhiclutils_README.md
    ├── STATE_MANAGEMENT_GUIDE.md
    ├── TROUBLESHOOTING_GUIDE.md
    ├── FILE_FORMATS.md
    └── EXIT_CODES.md
```

## Configuration

The archiver is configured via `config.yaml`. Key configuration sections:

- **`app`**: Application settings (working directory, state files, parallel workers)
- **`source_files`**: Source filesystem paths and run number extraction patterns
- **`artdaq_db`**: ArtdaqDB connection and operation settings
- **`ucon_db`**: UconDB server connection and credentials
- **`fhiclize_generate`**: FHiCL conversion and generation options
- **`reporting`**: Email and Slack notification settings (optional)
- **`carbon`**: Metrics reporting configuration (optional)

See [config.yaml.template](config.yaml.template) for detailed parameter documentation.

## Command-Line Interface

### Execution Modes

```bash
# Normal mode: both stages in sequence
./run_archiver.sh config.yaml

# Stage-specific execution
./run_archiver.sh config.yaml --import-only
./run_archiver.sh config.yaml --migrate-only

# Retry failed runs
./run_archiver.sh config.yaml --retry-failed-import
./run_archiver.sh config.yaml --retry-failed-migrate

# State recovery (rebuild from data sources)
./run_archiver.sh config.yaml --recover-import-state
./run_archiver.sh config.yaml --recover-migrate-state

# Status reporting
./run_archiver.sh config.yaml --report-status
./run_archiver.sh config.yaml --report-status --compare-state
```

### Additional Flags

- **`--incremental`**: Process only runs newer than last successful contiguous run
- **`-v, --verbose`**: Enable DEBUG logging
- **`--compare-state`**: Compare current status with saved state (used with `--report-status`)

See [OPERATIONS_MANUAL.md](documentation/OPERATIONS_MANUAL.md) for detailed usage patterns.

## Monitoring & Alerting

The archiver provides multiple monitoring mechanisms:

- **Log Files**: Structured logging with rotation support
- **Status Reports**: Comprehensive run availability analysis across all data sources
- **Email Notifications**: Automatic alerts on failures (configurable)
- **Slack Integration**: Real-time notifications via Slack webhooks (optional)
- **Carbon Metrics**: Performance metrics to Graphite/Carbon (optional)

See [OPERATIONS_MANUAL.md](documentation/OPERATIONS_MANUAL.md#monitoring) for monitoring setup.

## Common Operations

### Daily Incremental Run

```bash
# Run via cron to process new runs
0/10 * * * * /path/to/dist/run_archiver.sh /path/to/config.yaml --incremental
```

### Status Check

```bash
# Generate comprehensive status report
./run_archiver.sh config.yaml --report-status --compare-state
```

### Failure Recovery

```bash
# Retry failed imports
./run_archiver.sh config.yaml --retry-failed-import

# Retry failed migrations
./run_archiver.sh config.yaml --retry-failed-migrate
```

### State Recovery (Lost State Files)

```bash
# Rebuild import state from filesystem and artdaqDB
./run_archiver.sh config.yaml --recover-import-state

# Rebuild migration state from artdaqDB and UconDB
./run_archiver.sh config.yaml --recover-migrate-state
```

## Troubleshooting

### Common Issues

1. **Import Failures**: Check filesystem permissions, FHiCL conversion errors, artdaqDB connectivity
2. **Migration Failures**: Verify artdaqDB exports, blob creation, UconDB connectivity
3. **Performance Issues**: Adjust `parallel_workers`, consider CLI tools mode (`use_tools: true`)
4. **State Inconsistencies**: Use recovery modes to rebuild from data sources

See [TROUBLESHOOTING_GUIDE.md](documentation/TROUBLESHOOTING_GUIDE.md) for detailed diagnostics and solutions.

### Debug Mode

Enable verbose logging to diagnose issues:

```bash
./run_archiver.sh config.yaml -v
```

## Dependencies

The distribution package includes all required dependencies bundled in the `lib/` directory:

- **conftoolp**: artdaq_database Python bindings (bundled)
- **ucondb**: UconDB client library
- **pyyaml**: YAML configuration parsing
- **requests**: HTTP client for UconDB API
- **psycopg2-binary**: PostgreSQL driver (for ucondb)
- **slack-bolt**: Slack integration (optional)

No external artdaq_database environment setup is required.

## Development

This is a production distribution package. For development information, refer to the source repository documentation.

## Performance Notes

- **Typical Throughput**: 10-30 runs/minute depending on run size and configuration
- **Parallel Workers**: Default 2
- **CLI Tools Mode**: Enable `artdaq_db.use_tools: true` for 2-3x performance improvement on large batches

See [OPERATIONS_MANUAL.md](documentation/OPERATIONS_MANUAL.md#performance-tuning) for optimization guidance.

## Exit Codes

- **0**: Success
- **1**: Known error (configuration, database, validation errors)
- **2**: Unexpected error (uncaught exceptions)

See [EXIT_CODES.md](documentation/EXIT_CODES.md) for complete exit code reference.

## Support

For issues, questions, or feature requests:

1. Check [TROUBLESHOOTING_GUIDE.md](documentation/TROUBLESHOOTING_GUIDE.md)
2. Review relevant documentation in the `documentation/` directory
3. Contact the development team or system administrator

## License

This software is part of the sbndaq data acquisition framework ecosystem. Refer to your organization's licensing terms.
