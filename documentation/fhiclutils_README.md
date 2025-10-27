# FHiCL Utils Package

The `fhiclutils` package provides utilities for converting run record text files into FHiCL (Fermilab Hierarchical Configuration Language) format and validating the output. These Python implementations replace the original AWK scripts with improved maintainability, testability, and error handling.

## Package Overview

The fhiclutils package consists of three modules:

- **`converters.py`**: Functions that convert various run record text formats to FHiCL
- **`validator.py`**: FHiCL validation using the `fhicl-dump` utility
- **`utils.py`**: Common utility functions for FHiCL operations

## Module: converters.py

The converters module provides functions that transform run record text files into FHiCL format. Each converter handles a specific file type and applies the appropriate transformation rules.

### Available Converters

#### fhiclize_known_boardreaders_list(content: str) -> str

Converts `known_boardreaders_list.txt` to FHiCL format. Transforms space-separated values into key-value pairs with array values.

**Input Format:**
```
# Comment lines are ignored
tpc01 localhost -1
tpc02 myexp-tpc02 -1
pmt01 myexp-daq33-priv -1
```

**Output Format:**
```
tpc01: ["localhost", "-1"]
tpc02: ["myexp-tpc02", "-1"]
pmt01: ["myexp-daq33-priv", "-1"]
```

**Conversion Logic:**
- Skips comment lines (starting with `#`)
- Skips blank lines
- Parses quoted strings correctly
- First token becomes key
- Remaining tokens become quoted array elements
- Preserves quoted strings if present in input

**Example:**
```python
from run_record_archiver.fhiclutils.converters import fhiclize_known_boardreaders_list

input_text = """# Configuration
tpc01 localhost -1
tpc02 "myexp-tpc02" -1
"""

output = fhiclize_known_boardreaders_list(input_text)
print(output)
# Output:
# tpc01: ["localhost", "-1"]
# tpc02: ["myexp-tpc02", "-1"]
```

#### generate_run_history(metadata_content: str, run_number: Optional[int] = None) -> str

Generates `RunHistory.fcl` from metadata file content. Extracts configuration name and components list.

**Input Format (from metadata.txt):**
```
Config name: standard_myexp
Component #0: tpc01
Component #1: tpc02
Component #2: pmt01
```

**Output Format:**
```
run_number: 19661

config_name: "standard_myexp"

components: ["tpc01", "tpc02", "pmt01"]
```

**Conversion Logic:**
- Extracts `Config name:` line
- Extracts all `Component #N:` lines
- Optionally adds run number (if provided)
- Formats components as FHiCL array

**Example:**
```python
from run_record_archiver.fhiclutils.converters import generate_run_history

metadata = """Config name: standard_myexp
Component #0: tpc01
Component #1: tpc02
"""

output = generate_run_history(metadata, run_number=19661)
print(output)
# Output:
# run_number: 19661
#
# config_name: "standard_myexp"
#
# components: ["tpc01", "tpc02"]
```

#### fhiclize_metadata(content: str) -> str

Converts `metadata.txt` to FHiCL format. Handles complex structure including logfile sections and component aggregation.

**Input Format:**
```
Config name: standard_myexp
DAQInterface start time: 2025-10-24 10:30:00
Total events: 12345
Component #0: tpc01
Component #1: tpc02

boardreader logfiles:
tpc01-log.txt
tpc02-log.txt

eventbuilder logfiles:
eb01-log.txt
```

**Output Format:**
```
config_name: "standard_myexp"
daqinterface_start_time: "2025-10-24 10:30:00"
total_events: "12345"

components: ["tpc01", "tpc02"]

boardreader_logfiles: ["tpc01-log.txt", "tpc02-log.txt"]

eventbuilder_logfiles: ["eb01-log.txt"]
```

**Conversion Logic:**
- Converts keys to lowercase with underscores
- Aggregates components into array
- Handles logfile sections (boardreader, eventbuilder, datalogger, dispatcher, routingmanager, process_manager)
- Special handling for `commit/version` field (converts to `commit_or_version`)
- Special handling for `pmt logfile` (converts to `pmt_logfiles_wildcard`)
- Quotes string values
- Preserves numeric values

**Key Features:**
- **Component Aggregation**: Collects all `Component #N:` entries into a single array
- **Logfile Sections**: Multi-line sections terminated by blank line
- **Section Finalization**: Only dispatcher section finalized at EOF (matches AWK behavior)

**Example:**
```python
from run_record_archiver.fhiclutils.converters import fhiclize_metadata

input_text = """Config name: standard
DAQInterface start time: 2025-10-24 10:30:00
Component #0: tpc01
Component #1: tpc02

boardreader logfiles:
tpc01-log.txt
tpc02-log.txt
"""

output = fhiclize_metadata(input_text)
print(output)
# Output includes:
# config_name: "standard"
# daqinterface_start_time: "2025-10-24 10:30:00"
# components: ["tpc01", "tpc02"]
# boardreader_logfiles: ["tpc01-log.txt", "tpc02-log.txt"]
```

#### fhiclize_boot(content: str) -> str

Converts `boot.txt` to FHiCL format. Transforms process and subsystem settings into structured arrays.

**Input Format:**
```
BoardReader_host tpc01: localhost
BoardReader_port tpc01: 5200
BoardReader_label tpc01: tpc01
BoardReader_subsystem tpc01: tpc

EventBuilder_host eb01: myexp-daq33
EventBuilder_port eb01: 5250
EventBuilder_label eb01: eb01

Subsystem_id tpc: 1
Subsystem_source tpc: TPC
Subsystem_destination tpc: /data
```

**Output Format:**
```
subsystem_settings: [
{
id: "1"
source: "TPC"
destination: "/data"
}
]

artdaq_process_settings: [
{
name: "BoardReader"
label: "tpc01"
host: "localhost"
port: 5200
subsystem: "tpc"
},
{
name: "EventBuilder"
label: "eb01"
host: "myexp-daq33"
port: 5250
}
]
```

**Conversion Logic:**
- Detects process types: BoardReader, EventBuilder, DataLogger, Dispatcher, RoutingManager
- Extracts process attributes: host, port, label, subsystem
- Detects subsystem settings: id, source, destination
- Groups by label/id using blank line separators
- Uses `"not set"` as default for missing values
- Formats as structured FHiCL arrays

**Example:**
```python
from run_record_archiver.fhiclutils.converters import fhiclize_boot

input_text = """BoardReader_host tpc01: localhost
BoardReader_port tpc01: 5200
BoardReader_label tpc01: tpc01

EventBuilder_host eb01: myexp-daq33
EventBuilder_label eb01: eb01
"""

output = fhiclize_boot(input_text)
# Output contains artdaq_process_settings array with tpc01 and eb01
```

#### fhiclize_settings(content: str) -> str

Converts `settings.txt` to FHiCL format. Handles key-value pairs with type detection and array normalization.

**Input Format:**
```
max_fragment_size_bytes: 16777216
use_routing_manager: true
daq_setup_script: /path/to/setup.sh
dispatcher_hosts: [myexp-daq31, myexp-daq32, myexp-daq33]
```

**Output Format:**
```
max_fragment_size_bytes: 16777216
use_routing_manager: true
daq_setup_script: "/path/to/setup.sh"
dispatcher_hosts: [ myexp_daq31, myexp_daq32, myexp_daq33 ]
```

**Conversion Logic:**
- Normalizes keys (spaces/hyphens → underscores)
- Detects numeric values (preserved as-is)
- Detects boolean values (`true`/`false`)
- Quotes string values
- Normalizes array elements (removes quotes, replaces hyphens)
- Handles existing array syntax `[...]`

**Example:**
```python
from run_record_archiver.fhiclutils.converters import fhiclize_settings

input_text = """max_events: 10000
debug_mode: true
data_directory: /data/runs
hosts: [host-1, host-2]
"""

output = fhiclize_settings(input_text)
# Output:
# max_events: 10000
# debug_mode: true
# data_directory: "/data/runs"
# hosts: [ host_1, host_2 ]
```

#### fhiclize_setup(content: str) -> str

Converts `setup.txt` (bash setup script) to FHiCL format. Escapes content as single string value.

**Input Format:**
```bash
#!/bin/bash
source /daq/setup.sh
export DAQ_HOME="/daq"
echo "Setup complete"
```

**Output Format:**
```
setup_script: "#!/bin/bash\nsource /daq/setup.sh\nexport DAQ_HOME=\"/daq\"\necho \"Setup complete\""
```

**Conversion Logic:**
- Cleans non-ASCII characters (replaces with `.`)
- Escapes backslashes (`\` → `\\`)
- Escapes quotes (`"` → `\"`)
- Converts newlines to `\n`
- Wraps entire content in quotes

**Example:**
```python
from run_record_archiver.fhiclutils.converters import fhiclize_setup

input_text = """#!/bin/bash
source /daq/setup.sh
export PATH="/daq/bin:$PATH"
"""

output = fhiclize_setup(input_text)
# Output: setup_script: "#!/bin/bash\nsource /daq/setup.sh\nexport PATH=\"/daq/bin:$PATH\"\n"
```

#### fhiclize_environment(content: str) -> str

Converts `environment.txt` (bash export statements) to FHiCL format. Extracts environment variables.

**Input Format:**
```bash
export ARTDAQ_VERSION="v3_12_00"
export DAQ_HOME="/daq"
export FHICL_FILE_PATH="/daq/fcl"
```

**Output Format:**
```
ARTDAQ_VERSION: "v3_12_00"
DAQ_HOME: "/daq"
FHICL_FILE_PATH: "/daq/fcl"
```

**Conversion Logic:**
- Matches lines starting with `export`
- Extracts variable name and value
- Strips quotes from values
- Cleans non-ASCII characters
- Escapes quotes in values
- Skips non-export lines

**Example:**
```python
from run_record_archiver.fhiclutils.converters import fhiclize_environment

input_text = """export ARTDAQ_VERSION="v3_12_00"
export DAQ_HOME=/daq
# Comment line
export DEBUG_MODE="true"
"""

output = fhiclize_environment(input_text)
# Output:
# ARTDAQ_VERSION: "v3_12_00"
# DAQ_HOME: "/daq"
# DEBUG_MODE: "true"
```

#### fhiclize_ranks(content: str) -> str

Converts `ranks.txt` (process rank information) to FHiCL format. Creates structured rank table.

**Input Format:**
```
host        label       port    subsystem    rank
localhost   tpc01       5200    tpc          0
localhost   tpc02       5201    tpc          1
myexp-daq33  eb01        5250    daq          2
```

**Output Format:**
```
ranks: {
  header: ["host", "label", "port", "subsystem", "rank"]
  rank0: ["localhost", "tpc01", "5200", "tpc", "0"]
  rank1: ["localhost", "tpc02", "5201", "tpc", "1"]
  rank2: ["myexp-daq33", "eb01", "5250", "daq", "2"]
}
```

**Conversion Logic:**
- First non-comment line is header
- Subsequent lines are data rows
- Uses rank number (5th column) as key
- All values quoted in output
- Creates nested structure with header and rank entries

**Example:**
```python
from run_record_archiver.fhiclutils.converters import fhiclize_ranks

input_text = """host    label    port    subsystem    rank
localhost    tpc01    5200    tpc    0
localhost    tpc02    5201    tpc    1
"""

output = fhiclize_ranks(input_text)
# Output:
# ranks: {
#   header: ["host", "label", "port", "subsystem", "rank"]
#   rank0: ["localhost", "tpc01", "5200", "tpc", "0"]
#   rank1: ["localhost", "tpc02", "5201", "tpc", "1"]
# }
```

### Converter Usage Pattern

All converters follow a consistent pattern:

```python
from pathlib import Path
from run_record_archiver.fhiclutils.converters import (
    fhiclize_metadata,
    fhiclize_boot,
    fhiclize_known_boardreaders_list
)

# Read input file
run_dir = Path("/daq/run_records/19661")
metadata_file = run_dir / "metadata.txt"
content = metadata_file.read_text()

# Convert to FHiCL
fhicl_output = fhiclize_metadata(content)

# Write output file
output_file = run_dir / "metadata.fcl"
output_file.write_text(fhicl_output)
```

## Module: validator.py

The validator module provides FHiCL validation using the `fhicl-dump` utility from the artdaq_database suite.

### Validation Functions

#### validate_fhicl(content: Optional[str] = None, file_path: Optional[Path] = None, fhicl_dump_path: str = 'fhicl-dump') -> Tuple[bool, str]

Low-level validation function. Validates either content string or file path.

**Parameters:**
- `content`: FHiCL content string (optional)
- `file_path`: Path to FHiCL file (optional)
- `fhicl_dump_path`: Path to fhicl-dump utility (default: 'fhicl-dump')

**Returns:**
- Tuple of `(is_valid, message)`
  - `is_valid`: `True` if valid, `False` otherwise
  - `message`: Success message or error details

**Raises:**
- `ValueError`: If neither content nor file_path provided
- `FileNotFoundError`: If fhicl-dump not found

**Example:**
```python
from run_record_archiver.fhiclutils.validator import validate_fhicl

# Validate content string
fhicl_content = 'key: "value"\nanother_key: 123'
is_valid, message = validate_fhicl(content=fhicl_content)
if is_valid:
    print("Valid FHiCL")
else:
    print(f"Invalid: {message}")

# Validate file
is_valid, message = validate_fhicl(file_path=Path("/tmp/config.fcl"))
```

#### validate_fhicl_file(file_path: Path, fhicl_dump_path: str = 'fhicl-dump') -> Tuple[bool, str]

Validates a FHiCL file. Convenience wrapper for file validation.

**Parameters:**
- `file_path`: Path to FHiCL file
- `fhicl_dump_path`: Path to fhicl-dump utility (default: 'fhicl-dump')

**Returns:**
- Tuple of `(is_valid, message)`

**Example:**
```python
from pathlib import Path
from run_record_archiver.fhiclutils.validator import validate_fhicl_file

fcl_file = Path("/daq/run_records/19661/metadata.fcl")
is_valid, message = validate_fhicl_file(fcl_file)

if not is_valid:
    print(f"Validation failed: {message}")
```

#### validate_fhicl_content(content: str, fhicl_dump_path: str = 'fhicl-dump') -> Tuple[bool, str]

Validates FHiCL content string. Convenience wrapper for content validation.

**Parameters:**
- `content`: FHiCL content string
- `fhicl_dump_path`: Path to fhicl-dump utility (default: 'fhicl-dump')

**Returns:**
- Tuple of `(is_valid, message)`

**Example:**
```python
from run_record_archiver.fhiclutils.validator import validate_fhicl_content
from run_record_archiver.fhiclutils.converters import fhiclize_metadata

# Convert and validate
input_text = metadata_file.read_text()
fhicl_output = fhiclize_metadata(input_text)
is_valid, message = validate_fhicl_content(fhicl_output)

if not is_valid:
    print(f"Converter produced invalid FHiCL: {message}")
```

### Validation Implementation Details

The validation process:

1. **Temp File Creation**: Content validation creates temporary `.fcl` file
2. **Environment Setup**: Sets `FHICL_FILE_PATH` to file's directory
3. **fhicl-dump Execution**: Runs `fhicl-dump --quiet <file>`
4. **Result Analysis**: 
   - Exit code 0 → Valid
   - Non-zero → Invalid, returns stderr/stdout
5. **Cleanup**: Removes temporary file (content validation only)
6. **Timeout**: 10-second timeout prevents hanging

**Error Messages:**
- Syntax errors from fhicl-dump
- File not found errors
- Permission errors
- Timeout errors

**Example with Error Handling:**
```python
from run_record_archiver.fhiclutils.validator import validate_fhicl_content
from run_record_archiver.fhiclutils.converters import fhiclize_boot

try:
    content = boot_file.read_text()
    fhicl_output = fhiclize_boot(content)
    is_valid, message = validate_fhicl_content(fhicl_output, fhicl_dump_path="lib/fhicl-dump")
    
    if is_valid:
        print("Conversion successful")
        output_file.write_text(fhicl_output)
    else:
        print(f"Validation failed: {message}")
        print(f"Generated FHiCL:\n{fhicl_output}")
        
except FileNotFoundError as e:
    print(f"fhicl-dump not found: {e}")
except Exception as e:
    print(f"Validation error: {e}")
```

## Module: utils.py

The utils module provides common utility functions used across converters.

### Utility Functions

#### is_numeric(value: str) -> bool

Checks if a string represents a numeric value (integer or float).

**Parameters:**
- `value`: String to check

**Returns:**
- `True` if numeric, `False` otherwise

**Logic:**
- Allows digits and decimal point
- Maximum one decimal point
- Handles integers and floats

**Example:**
```python
from run_record_archiver.fhiclutils.utils import is_numeric

print(is_numeric("123"))      # True
print(is_numeric("123.456"))  # True
print(is_numeric("123.45.6")) # False (multiple dots)
print(is_numeric("abc"))      # False
print(is_numeric(""))         # False
```

#### normalize_key(key: str) -> str

Normalizes a key string by replacing whitespace, hyphens, and special characters with underscores.

**Parameters:**
- `key`: Key string to normalize

**Returns:**
- Normalized key string

**Logic:**
- Replaces: spaces, hyphens, parentheses, slashes, hash, dots
- Converts to underscores
- Strips leading/trailing whitespace first

**Example:**
```python
from run_record_archiver.fhiclutils.utils import normalize_key

print(normalize_key("DAQ Setup Script"))        # "DAQ_Setup_Script"
print(normalize_key("max-fragment-size"))       # "max_fragment_size"
print(normalize_key("process (type)"))          # "process__type_"
print(normalize_key("commit/version"))          # "commit_version"
```

#### quote_value(value: str) -> str

Quotes a string value for FHiCL format. Smart quoting based on value type.

**Parameters:**
- `value`: Value to quote

**Returns:**
- Quoted or unquoted value (based on type)

**Logic:**
- Already quoted → returns as-is
- Array syntax `[...]` → returns as-is
- Numeric value → returns as-is
- String → adds quotes and escapes internal quotes

**Example:**
```python
from run_record_archiver.fhiclutils.utils import quote_value

print(quote_value("hello"))           # "hello"
print(quote_value('"hello"'))         # "hello" (already quoted)
print(quote_value("123"))             # 123 (numeric)
print(quote_value("[1,2,3]"))         # [1,2,3] (array)
print(quote_value('say "hi"'))        # "say \"hi\"" (escapes quote)
```

#### format_fhicl_array(items: List[str]) -> str

Formats a list of strings as a FHiCL array with quoted elements.

**Parameters:**
- `items`: List of strings

**Returns:**
- FHiCL array string

**Logic:**
- Empty list → `[]`
- Quotes each item
- Comma-separated
- Wrapped in brackets

**Example:**
```python
from run_record_archiver.fhiclutils.utils import format_fhicl_array

print(format_fhicl_array([]))                           # []
print(format_fhicl_array(["tpc01"]))                   # ["tpc01"]
print(format_fhicl_array(["tpc01", "tpc02", "pmt01"])) # ["tpc01", "tpc02", "pmt01"]
```

#### clean_non_ascii(text: str) -> str

Removes non-ASCII characters from text. Replaces with periods.

**Parameters:**
- `text`: Input text

**Returns:**
- ASCII-only text

**Logic:**
- Keeps characters with ord < 128
- Replaces others with `.`

**Example:**
```python
from run_record_archiver.fhiclutils.utils import clean_non_ascii

print(clean_non_ascii("hello world"))       # "hello world"
print(clean_non_ascii("café"))              # "caf."
print(clean_non_ascii("test™"))             # "test."
```

#### strip_comments(line: str) -> str

Removes inline comments from a line.

**Parameters:**
- `line`: Input line

**Returns:**
- Line with comment removed

**Logic:**
- Finds `#` character
- Returns everything before it
- Strips whitespace

**Example:**
```python
from run_record_archiver.fhiclutils.utils import strip_comments

print(strip_comments("key: value # comment"))  # "key: value"
print(strip_comments("key: value"))            # "key: value"
print(strip_comments("# full comment"))        # ""
```

### Utility Usage Example

Here's how utilities are used in converters:

```python
from run_record_archiver.fhiclutils.utils import (
    normalize_key,
    quote_value,
    is_numeric,
    format_fhicl_array
)

def convert_line(line: str) -> str:
    """Convert a key-value line to FHiCL format."""
    if ':' not in line:
        return ""
    
    key, value = line.split(':', 1)
    key = normalize_key(key)
    value = value.strip()
    
    if is_numeric(value):
        return f"{key}: {value}"
    else:
        return f"{key}: {quote_value(value)}"

def convert_array(items: List[str]) -> str:
    """Convert a list to FHiCL array format."""
    return format_fhicl_array(items)

# Usage
result = convert_line("Max Events: 10000")
# Output: "max_events: 10000"

result = convert_line("Config Name: standard")
# Output: "config_name: \"standard\""

result = convert_array(["tpc01", "tpc02"])
# Output: ["tpc01", "tpc02"]
```

## Adding New Converters

When adding a new converter function, follow these guidelines:

### 1. Implement Converter Function

Create a new function in `converters.py`:

```python
def fhiclize_new_format(content: str) -> str:
    """Convert new format to FHiCL.
    
    Args:
        content: Input file content
        
    Returns:
        FHiCL formatted string
    """
    lines = []
    
    for line in content.splitlines():
        # Skip comments and blank lines
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith('#'):
            continue
        
        # Parse and convert line
        # ... conversion logic ...
        
        lines.append(converted_line)
    
    # Add trailing newline (matches AWK behavior)
    return '\n'.join(lines) + '\n' if lines else ''
```

### 2. Add Unit Tests

Create tests in `tests/test_fhicl_converters.py`:

```python
def test_new_format_basic(fhicl_dump_path):
    """Test basic new format conversion."""
    input_text = """# Test input
key1: value1
key2: 123
"""
    
    result = fhiclize_new_format(input_text)
    
    assert 'key1: "value1"' in result
    assert 'key2: 123' in result
    
    # Validate with fhicl-dump
    validate_fhicl_output(result, fhicl_dump_path)
```

### 3. Add AWK Comparison (Optional)

If replacing an AWK script, add comparison test in `tests/test_fhicl_awk_comparison.py`:

```python
def test_new_format_awk_comparison():
    """Compare new format converter against AWK reference."""
    test_file = Path("/daq/run_records/19661/new_format.txt")
    awk_script = Path("tools/utils/fhiclize_new_format.awk")
    
    # Get AWK output
    awk_result = subprocess.run(
        ["awk", "-f", str(awk_script), str(test_file)],
        capture_output=True, text=True
    )
    
    # Get Python output
    python_result = fhiclize_new_format(test_file.read_text())
    
    # Compare
    assert awk_result.stdout == python_result
```

### 4. Update Configuration

Add to `config.yaml` and `config.yaml.template`:

```yaml
fhiclize_generate:
  convert:
    new_format:
      source_suffix: ".txt"
      target_suffix: ".fcl"
```

### 5. Update Documentation

- Add function to this README
- Update `tests/README_FHICL_TESTS.md` if adding tests
- Update `run_record_archiver/config.md` for configuration

### 6. Integration

Update `services/fcl_preparer.py` to use new converter:

```python
from ..fhiclutils.converters import fhiclize_new_format

def convert_file(self, file_path: Path) -> str:
    """Convert file based on type."""
    if file_path.name == "new_format.txt":
        content = file_path.read_text()
        return fhiclize_new_format(content)
    # ... other converters ...
```

## Testing Approach

The FHiCL utilities have comprehensive test coverage. See `tests/README_FHICL_TESTS.md` for complete testing documentation.

### Test Levels

#### 1. Unit Tests (`tests/test_fhicl_converters.py`)

Fast tests with no external dependencies. Test individual converters with sample data.

**Run:**
```bash
pytest tests/test_fhicl_converters.py -v
```

**Coverage:**
- Basic conversion logic
- Edge cases (empty input, comments, special characters)
- FHiCL validation of output
- Error handling

#### 2. AWK Comparison Tests (`tests/test_fhicl_awk_comparison.py`)

Validates Python converters against AWK reference implementations across 200 production runs.

**Run:**
```bash
# Enable in tests_config.yaml first
python tests/test_fhicl_awk_comparison.py
```

**Coverage:**
- Exact output matching with AWK
- Process ordering differences (sorted comparison)
- Real production data validation

#### 3. Debug Tools (`tests/debug_fhicl_failures.py`)

Investigates specific failed runs with detailed diffs.

**Run:**
```bash
python -m tests.debug_fhicl_failures 19661 19405
```

**Features:**
- Character-by-character comparison
- Unified diff format
- Invisible character detection

### Test Configuration

Control tests via `tests_config.yaml`:

```yaml
tests:
  test_fhicl_converters: true      # Unit tests (always enabled)
  test_fhicl_awk_comparison: false # AWK comparison (disabled by default, slow)
  test_fhicl_comprehensive: false  # Comprehensive tests (requires /daq/run_records)
```

### Example Test

```python
import pytest
from pathlib import Path
from run_record_archiver.fhiclutils.converters import fhiclize_metadata
from run_record_archiver.fhiclutils.validator import validate_fhicl_content

def test_metadata_conversion(fhicl_dump_path):
    """Test metadata conversion and validation."""
    input_text = """Config name: standard
DAQInterface start time: 2025-10-24 10:30:00
Total events: 12345
Component #0: tpc01
Component #1: tpc02
"""
    
    # Convert
    result = fhiclize_metadata(input_text)
    
    # Check content
    assert 'config_name: "standard"' in result
    assert 'daqinterface_start_time: "2025-10-24 10:30:00"' in result
    assert 'total_events: "12345"' in result
    assert 'components: ["tpc01", "tpc02"]' in result
    
    # Validate FHiCL syntax
    is_valid, message = validate_fhicl_content(result, fhicl_dump_path)
    assert is_valid, f"Invalid FHiCL: {message}\n{result}"
```

## Integration with Archiver

The fhiclutils package is integrated into the archiver through `services/fcl_preparer.py`:

```python
from pathlib import Path
from run_record_archiver.fhiclutils import (
    converters,
    validator,
    utils
)

class FclPreparer:
    """Prepares FHiCL files for archival."""
    
    def convert_files(self, run_dir: Path, output_dir: Path):
        """Convert all text files to FHiCL format."""
        
        # Convert metadata.txt → metadata.fcl
        metadata_txt = run_dir / "metadata.txt"
        if metadata_txt.exists():
            content = metadata_txt.read_text()
            fhicl = converters.fhiclize_metadata(content)
            
            # Validate
            is_valid, msg = validator.validate_fhicl_content(fhicl)
            if not is_valid:
                raise ValueError(f"Invalid FHiCL: {msg}")
            
            # Write output
            output_file = output_dir / "metadata.fcl"
            output_file.write_text(fhicl)
        
        # Convert boot.txt → boot.fcl
        boot_txt = run_dir / "boot.txt"
        if boot_txt.exists():
            content = boot_txt.read_text()
            fhicl = converters.fhiclize_boot(content)
            
            # Validate and write
            is_valid, msg = validator.validate_fhicl_content(fhicl)
            if is_valid:
                (output_dir / "boot.fcl").write_text(fhicl)
        
        # Generate RunHistory.fcl
        if metadata_txt.exists():
            content = metadata_txt.read_text()
            run_number = int(run_dir.name)
            run_history = converters.generate_run_history(content, run_number)
            (output_dir / "RunHistory.fcl").write_text(run_history)
```

## Configuration

FHiCL converter behavior is configured in `config.yaml`:

```yaml
fhiclize_generate:
  # File conversions (source → target)
  convert:
    metadata:
      source_suffix: ".txt"
      target_suffix: ".fcl"
    boot:
      source_suffix: ".txt"
      target_suffix: ".fcl"
    known_boardreaders_list:
      source_suffix: ".txt"
      target_suffix: ".fcl"
    settings:
      source_suffix: ".txt"
      target_suffix: ".fcl"
    setup:
      source_suffix: ".txt"
      target_suffix: ".fcl"
    environment:
      source_suffix: ".txt"
      target_suffix: ".fcl"
    ranks:
      source_suffix: ".txt"
      target_suffix: ".fcl"
  
  # Generated files (no source file required)
  generate:
    - "RunHistory.fcl"
```

See `run_record_archiver/config.md` for complete configuration documentation.

## Common Patterns

### Error Handling

```python
from run_record_archiver.fhiclutils.converters import fhiclize_metadata
from run_record_archiver.fhiclutils.validator import validate_fhicl_content

try:
    # Convert
    content = file_path.read_text()
    fhicl_output = fhiclize_metadata(content)
    
    # Validate
    is_valid, message = validate_fhicl_content(fhicl_output)
    if not is_valid:
        logger.error("Validation failed: %s", message)
        logger.debug("Generated FHiCL:\n%s", fhicl_output)
        raise ValueError(f"Invalid FHiCL: {message}")
    
    # Write output
    output_path.write_text(fhicl_output)
    logger.info("Converted %s → %s", file_path.name, output_path.name)
    
except FileNotFoundError as e:
    logger.error("Input file not found: %s", e)
except ValueError as e:
    logger.error("Conversion error: %s", e)
except Exception as e:
    logger.exception("Unexpected error: %s", e)
```

### Batch Conversion

```python
from pathlib import Path
from run_record_archiver.fhiclutils.converters import (
    fhiclize_metadata,
    fhiclize_boot,
    fhiclize_known_boardreaders_list
)

def convert_run_directory(run_dir: Path, output_dir: Path):
    """Convert all text files in run directory to FHiCL."""
    
    converters_map = {
        "metadata.txt": fhiclize_metadata,
        "boot.txt": fhiclize_boot,
        "known_boardreaders_list.txt": fhiclize_known_boardreaders_list,
    }
    
    for source_file, converter_func in converters_map.items():
        input_path = run_dir / source_file
        if not input_path.exists():
            continue
        
        # Convert
        content = input_path.read_text()
        fhicl_output = converter_func(content)
        
        # Write
        output_file = output_dir / source_file.replace('.txt', '.fcl')
        output_file.write_text(fhicl_output)
        print(f"✓ {source_file} → {output_file.name}")
```

### Custom Validation Path

```python
from run_record_archiver.fhiclutils.validator import validate_fhicl_content

# Use custom fhicl-dump path
fhicl_dump = "/path/to/custom/lib/fhicl-dump"
is_valid, message = validate_fhicl_content(fhicl_output, fhicl_dump_path=fhicl_dump)

# Check environment
import shutil
fhicl_dump = shutil.which("fhicl-dump")
if not fhicl_dump:
    print("fhicl-dump not found in PATH")
else:
    is_valid, message = validate_fhicl_content(fhicl_output, fhicl_dump_path=fhicl_dump)
```

## Best Practices

1. **Always validate output**: Use `validate_fhicl_content()` after conversion
2. **Add trailing newlines**: All converters should end output with `\n`
3. **Handle blank lines**: Use blank lines as section separators (like boot.txt)
4. **Preserve comments**: Skip comment lines but preserve structure
5. **Quote strings**: Use `quote_value()` for consistent quoting
6. **Normalize keys**: Use `normalize_key()` for consistent key formatting
7. **Clean input**: Use `clean_non_ascii()` for setup/environment files
8. **Test with real data**: Use AWK comparison tests with production data
9. **Use utilities**: Leverage `utils.py` functions for consistency
10. **Document edge cases**: Add comments for non-obvious behavior

## Performance Considerations

- Converters process files line-by-line (memory efficient)
- Validation creates temporary files (I/O overhead)
- fhicl-dump subprocess has 10-second timeout
- Large files (>1MB) may require special handling
- Batch conversion can be parallelized

## Related Documentation

- FHiCL test documentation: `/tests/README_FHICL_TESTS.md`
- Configuration guide: `/run_record_archiver/config.md`
- FCL Preparer service: `/run_record_archiver/importer.md` (section on FHiCL preparation)
- Main documentation: `/run_record_archiver/readme.md`
- Build instructions: `/run_record_archiver/build.md` (fhicl-dump setup)
