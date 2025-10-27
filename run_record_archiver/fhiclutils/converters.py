import re
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from .utils import is_numeric, normalize_key, quote_value, format_fhicl_array, clean_non_ascii, strip_comments

def fhiclize_known_boardreaders_list(content: str) -> str:
    lines = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = []
        in_quote = False
        current_part = []
        i = 0
        while i < len(line):
            char = line[i]
            if char == '"' and (not in_quote):
                in_quote = True
                current_part.append(char)
            elif char == '"' and in_quote:
                in_quote = False
                current_part.append(char)
                parts.append(''.join(current_part))
                current_part = []
            elif char.isspace() and (not in_quote):
                if current_part:
                    parts.append(''.join(current_part))
                    current_part = []
            else:
                current_part.append(char)
            i += 1
        if current_part:
            parts.append(''.join(current_part))
        if len(parts) < 2:
            continue
        key = parts[0]
        values = parts[1:]
        quoted_values = []
        has_quoted_string = False
        for v in values:
            if v.startswith('"') and v.endswith('"'):
                quoted_values.append(v)
                has_quoted_string = True
            else:
                quoted_values.append(f'"{v}"')
        if has_quoted_string:
            array_str = '[' + ', '.join(quoted_values) + ' ]'
        else:
            array_str = '[' + ', '.join(quoted_values) + ']'
        lines.append(f'{key}: {array_str}')
    return '\n'.join(lines) + '\n' if lines else ''

def generate_run_history(metadata_content: str, run_number: Optional[int]=None) -> str:
    config_name = None
    components = []
    for line in metadata_content.splitlines():
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith('#'):
            continue
        if (match := re.match('^Config name:\\s*(.+)', line_stripped)):
            config_name = match.group(1).strip()
        elif (match := re.match('^Component #\\d+:\\s*(.+)', line_stripped)):
            component = match.group(1).strip()
            components.append(component)
    lines = []
    if run_number is not None:
        lines.append(f'run_number: {run_number}')
        lines.append('')
    if config_name:
        lines.append(f'config_name: "{config_name}"')
        lines.append('')
    if components:
        lines.append(f'components: {format_fhicl_array(components)}')
        lines.append('')
    return '\n'.join(lines) + '\n' if lines else ''

def fhiclize_metadata(content: str) -> str:
    lines = []
    components = []
    process_managers = []
    boardreaders = []
    eventbuilders = []
    routingmanagers = []
    dataloggers = []
    dispatchers = []
    in_process_manager_section = False
    in_boardreader_section = False
    in_eventbuilder_section = False
    in_routingmanager_section = False
    in_datalogger_section = False
    in_dispatcher_section = False
    components_section_active = False

    def finalize_logfile_section(section_name: str, items: List[str], output: List[str]):
        output.append(f'\n{section_name}: {format_fhicl_array(items)}')
    for line in content.splitlines():
        original_line = line
        line_stripped = line.strip()
        if line_stripped.startswith('#'):
            lines.append(original_line)
            continue
        if not line_stripped:
            if in_process_manager_section:
                finalize_logfile_section('process_manager_logfiles', process_managers, lines)
                in_process_manager_section = False
            elif in_boardreader_section:
                finalize_logfile_section('boardreader_logfiles', boardreaders, lines)
                in_boardreader_section = False
            elif in_eventbuilder_section:
                finalize_logfile_section('eventbuilder_logfiles', eventbuilders, lines)
                in_eventbuilder_section = False
            elif in_routingmanager_section:
                finalize_logfile_section('routingmanager_logfiles', routingmanagers, lines)
                in_routingmanager_section = False
            elif in_datalogger_section:
                finalize_logfile_section('datalogger_logfiles', dataloggers, lines)
                in_datalogger_section = False
            elif in_dispatcher_section:
                finalize_logfile_section('dispatcher_logfiles', dispatchers, lines)
                in_dispatcher_section = False
            elif components_section_active:
                lines.append(f'components: {format_fhicl_array(components)}')
                components_section_active = False
            continue
        if in_process_manager_section or in_boardreader_section or in_eventbuilder_section or in_routingmanager_section or in_datalogger_section or in_dispatcher_section:
            if in_process_manager_section:
                process_managers.append(line_stripped.split()[0])
            elif in_boardreader_section:
                boardreaders.append(line_stripped.split()[0])
            elif in_eventbuilder_section:
                eventbuilders.append(line_stripped.split()[0])
            elif in_routingmanager_section:
                routingmanagers.append(line_stripped.split()[0])
            elif in_datalogger_section:
                dataloggers.append(line_stripped.split()[0])
            elif in_dispatcher_section:
                dispatchers.append(line_stripped.split()[0])
            continue
        if components_section_active and (not re.match('Component #\\d+', line_stripped)):
            lines.append(f'components: {format_fhicl_array(components)}')
            components_section_active = False
        colon_pos = line_stripped.find(':')
        if colon_pos == -1:
            continue
        key_part = line_stripped[:colon_pos].strip()
        value_part = line_stripped[colon_pos + 1:].strip()
        if re.match('Config name|DAQInterface start time|DAQInterface stop time|Total events', key_part):
            key_part = key_part.lower().replace(' ', '_')
            lines.append(f'{key_part}: {quote_value(value_part)}')
        elif re.match('Component #\\d+', key_part):
            components.append(value_part)
            components_section_active = True
        elif re.search('commit/version', key_part):
            key_part = re.sub('[\\s\\-]+', '_', key_part)
            key_part = key_part.replace('commit/version', 'commit_or_version')
            value_part = value_part.replace('"', ' ')
            lines.append(f'{key_part}: "{value_part}"')
        elif key_part == 'pmt logfile':
            lines.append(f'pmt_logfiles_wildcard: {quote_value(value_part)}')
        elif key_part == 'process management method':
            lines.append(f'process_management_method: {quote_value(value_part)}')
        elif key_part == 'process manager logfiles':
            in_process_manager_section = True
        elif key_part == 'boardreader logfiles':
            in_boardreader_section = True
        elif key_part == 'eventbuilder logfiles':
            in_eventbuilder_section = True
        elif key_part == 'routingmanager logfiles':
            in_routingmanager_section = True
        elif key_part == 'datalogger logfiles':
            in_datalogger_section = True
        elif key_part == 'dispatcher logfiles':
            in_dispatcher_section = True
        else:
            key_normalized = re.sub('[\\s\\-]+', '_', key_part)
            lines.append(f'{key_normalized}: {quote_value(value_part)}')
    if in_dispatcher_section:
        finalize_logfile_section('dispatcher_logfiles', dispatchers, lines)
    return '\n'.join(lines) + '\n' if lines else ''

def fhiclize_boot(content: str) -> str:
    simple_kvs = []
    processes = {}
    subsystems = {}
    current_process = {'name': 'not set', 'label': 'not set', 'host': 'not set', 'port': 'not set', 'subsystem': 'not set'}
    current_subsystem = {'id': 'not set', 'source': 'not set', 'destination': 'not set'}
    PROCESS_NAMES = ['BoardReader', 'EventBuilder', 'DataLogger', 'Dispatcher', 'RoutingManager']
    PROCESS_TOKENS = ['host', 'port', 'label', 'subsystem']
    SUBSYSTEM_TOKENS = ['id', 'source', 'destination']

    def finalize_process():
        if current_process['label'] != 'not set':
            processes[current_process['label']] = current_process.copy()
            current_process['name'] = 'not set'
            current_process['label'] = 'not set'
            current_process['host'] = 'not set'
            current_process['port'] = 'not set'
            current_process['subsystem'] = 'not set'

    def finalize_subsystem():
        if current_subsystem['id'] != 'not set':
            subsystems[current_subsystem['id']] = current_subsystem.copy()
            current_subsystem['id'] = 'not set'
            current_subsystem['source'] = 'not set'
            current_subsystem['destination'] = 'not set'
    for line in content.splitlines():
        line = line.strip()
        if line.startswith('#'):
            continue
        if not line:
            finalize_process()
            finalize_subsystem()
            continue
        colon_pos = line.find(':')
        if colon_pos == -1:
            continue
        key = line[:colon_pos].strip()
        value = line[colon_pos + 1:].strip()
        key_normalized = re.sub('\\s+', '_', key)
        matched_subsystem = False
        for token in SUBSYSTEM_TOKENS:
            if f'Subsystem_{token}' in key_normalized:
                if token == 'id':
                    current_subsystem['id'] = value
                elif token == 'source':
                    current_subsystem['source'] = value
                elif token == 'destination':
                    current_subsystem['destination'] = value
                matched_subsystem = True
                break
        if matched_subsystem:
            continue
        matched_process = False
        for process_name in PROCESS_NAMES:
            for token in PROCESS_TOKENS:
                if f'{process_name}_{token}' in key_normalized:
                    current_process['name'] = process_name
                    if token == 'label':
                        current_process['label'] = value
                    elif token == 'host':
                        current_process['host'] = value
                    elif token == 'port':
                        current_process['port'] = value
                    elif token == 'subsystem':
                        current_process['subsystem'] = value
                    matched_process = True
                    break
            if matched_process:
                break
        if matched_process:
            continue
        value_formatted = value if is_numeric(value) else quote_value(value)
        simple_kvs.append(f'{key_normalized}: {value_formatted}')
    finalize_process()
    finalize_subsystem()
    output_lines = []
    output_lines.extend(simple_kvs)
    if subsystems:
        output_lines.append('\nsubsystem_settings: [')
        for (idx, (sub_id, sub_data)) in enumerate(subsystems.items()):
            output_lines.append('{')
            output_lines.append(f'''id: "{sub_data['id']}"''')
            if sub_data['source'] != 'not set':
                output_lines.append(f'''source: "{sub_data['source']}"''')
            if sub_data['destination'] != 'not set':
                output_lines.append(f'''destination: "{sub_data['destination']}"''')
            if idx < len(subsystems) - 1:
                output_lines.append('},')
            else:
                output_lines.append('}')
        output_lines.append(']')
    output_lines.append('\nartdaq_process_settings: [')
    for (idx, (label, proc_data)) in enumerate(processes.items()):
        output_lines.append('{')
        output_lines.append(f'''name: "{proc_data['name']}"''')
        output_lines.append(f'''label: "{proc_data['label']}"''')
        output_lines.append(f'''host: "{proc_data['host']}"''')
        if proc_data['port'] != 'not set':
            output_lines.append(f"port: {proc_data['port']}")
        if proc_data['subsystem'] != 'not set':
            output_lines.append(f'''subsystem: "{proc_data['subsystem']}"''')
        if idx < len(processes) - 1:
            output_lines.append('},')
        else:
            output_lines.append('}')
    output_lines.append(']')
    return '\n'.join(output_lines) + '\n' if output_lines else ''

def fhiclize_settings(content: str) -> str:
    lines = []
    for line in content.splitlines():
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith('#'):
            continue
        colon_pos = line_stripped.find(':')
        if colon_pos == -1:
            continue
        key = line_stripped[:colon_pos].strip()
        value = line_stripped[colon_pos + 1:].strip()
        key_normalized = normalize_key(key)
        if value.startswith('['):
            array_content = value[1:-1]
            elements = [e.strip() for e in array_content.split(',')]
            normalized_elements = []
            for elem in elements:
                elem = elem.strip()
                if not elem:
                    continue
                if elem.startswith('"') and elem.endswith('"') or (elem.startswith("'") and elem.endswith("'")):
                    elem = elem[1:-1]
                elem = elem.replace('-', '_')
                normalized_elements.append(elem)
            lines.append(f"{key_normalized}: [ {', '.join(normalized_elements)} ]")
        elif is_numeric(value):
            lines.append(f'{key_normalized}: {value}')
        elif value.lower() in ('true', 'false'):
            lines.append(f'{key_normalized}: {value.lower()}')
        else:
            lines.append(f'{key_normalized}: {quote_value(value)}')
    return '\n'.join(lines) + '\n' if lines else ''

def fhiclize_setup(content: str) -> str:
    content = clean_non_ascii(content)
    content = content.replace('\\', '\\\\').replace('"', '\\"')
    content = content.replace('\n', '\\n')
    return f'setup_script: "{content}"'

def fhiclize_environment(content: str) -> str:
    lines = []
    for line in content.splitlines():
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith('#'):
            continue
        if (match := re.match('^export\\s+([A-Za-z_][A-Za-z0-9_]*)\\s*=\\s*(.*)$', line_stripped)):
            (key, value) = match.groups()
            value = value.strip().strip('\'"')
            value = clean_non_ascii(value)
            value = value.replace('"', '\\"')
            lines.append(f'{key}: "{value}"')
    return '\n'.join(lines) + '\n' if lines else ''

def fhiclize_ranks(content: str) -> str:
    header_line = None
    data_rows = []
    for line in content.splitlines():
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith('#'):
            continue
        parts = line_stripped.split()
        if not parts:
            continue
        if header_line is None:
            header_line = parts
            continue
        data_rows.append(parts)
    if not header_line:
        return ''
    output_lines = ['ranks: {']
    quoted_headers = [f'"{h}"' for h in header_line]
    output_lines.append(f"  header: [{', '.join(quoted_headers)}]")
    for row in data_rows:
        if len(row) >= 5:
            rank_num = row[4]
            quoted_values = [f'"{val}"' for val in row]
            output_lines.append(f"  rank{rank_num}: [{', '.join(quoted_values)}]")
    output_lines.append('}')
    return '\n'.join(output_lines) + '\n'