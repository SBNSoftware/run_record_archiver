import difflib
import hashlib
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
logger = logging.getLogger(__name__)

@dataclass
class DiffOptions:
    ignore_case: bool = False
    ignore_tab_expansion: bool = False
    ignore_trailing_space: bool = False
    ignore_space_change: bool = False
    ignore_all_space: bool = False
    ignore_blank_lines: bool = False
    ignore_matching_lines: Optional[str] = None

def compute_file_hash(file_path: Path) -> str:
    return hashlib.md5(file_path.read_bytes()).hexdigest()

def normalize_line(line: str, options: DiffOptions) -> str:
    if options.ignore_all_space:
        had_newline = line.endswith('\n')
        line = ''.join(line.split())
        if had_newline:
            line += '\n'
    elif options.ignore_space_change:
        line = re.sub('[ \\t]+', ' ', line)
    if options.ignore_tab_expansion:
        line = line.expandtabs(8)
    if options.ignore_trailing_space:
        line = line.rstrip() + ('\n' if line.endswith('\n') else '')
    if options.ignore_case:
        line = line.lower()
    return line

def should_ignore_line(line: str, options: DiffOptions) -> bool:
    line_stripped = line.rstrip('\n\r')
    if options.ignore_blank_lines and (not line_stripped):
        return True
    if options.ignore_matching_lines and re.search(options.ignore_matching_lines, line):
        return True
    return False

def generate_diff(file1: Path, file2: Path, filename: str, options: Optional[DiffOptions]=None) -> str:
    if options is None:
        options = DiffOptions()
    try:
        lines1 = file1.read_text(encoding='utf-8').splitlines(keepends=True)
        lines2 = file2.read_text(encoding='utf-8').splitlines(keepends=True)
    except UnicodeDecodeError:
        return f'{filename}: Binary files differ\n'
    if options.ignore_blank_lines or options.ignore_matching_lines:
        lines1 = [l for l in lines1 if not should_ignore_line(l, options)]
        lines2 = [l for l in lines2 if not should_ignore_line(l, options)]
    if any([options.ignore_case, options.ignore_tab_expansion, options.ignore_trailing_space, options.ignore_space_change, options.ignore_all_space]):
        lines1 = [normalize_line(l, options) for l in lines1]
        lines2 = [normalize_line(l, options) for l in lines2]
    diff_lines = list(difflib.unified_diff(lines1, lines2, fromfile=f'a/{filename}', tofile=f'b/{filename}', lineterm=''))
    if not diff_lines:
        return f'{filename}: Files are identical (but hashes differ?)\n'
    return '\n'.join(diff_lines) + '\n'

def files_are_identical(file1: Path, file2: Path, options: Optional[DiffOptions]=None) -> bool:
    if options is None:
        options = DiffOptions()
    try:
        lines1 = file1.read_text(encoding='utf-8').splitlines(keepends=True)
        lines2 = file2.read_text(encoding='utf-8').splitlines(keepends=True)
    except UnicodeDecodeError:
        return file1.read_bytes() == file2.read_bytes()
    if options.ignore_blank_lines or options.ignore_matching_lines:
        lines1 = [l for l in lines1 if not should_ignore_line(l, options)]
        lines2 = [l for l in lines2 if not should_ignore_line(l, options)]
    if any([options.ignore_case, options.ignore_tab_expansion, options.ignore_trailing_space, options.ignore_space_change, options.ignore_all_space]):
        lines1 = [normalize_line(l, options) for l in lines1]
        lines2 = [normalize_line(l, options) for l in lines2]
    return lines1 == lines2

class DiffAnalyzer:
    FLAG_CONFIGS = {'ignore-case': DiffOptions(ignore_case=True), 'ignore-tab-expansion': DiffOptions(ignore_tab_expansion=True), 'ignore-trailing-space': DiffOptions(ignore_trailing_space=True), 'ignore-space-change': DiffOptions(ignore_space_change=True), 'ignore-all-space': DiffOptions(ignore_all_space=True), 'ignore-blank-lines': DiffOptions(ignore_blank_lines=True)}
    STATUS_EMOJIS = {'identical': '✓', 'different': '✗', 'only1': '←', 'only2': '→', 'ignore-case': 'Aa', 'ignore-tab-expansion': '⇥', 'ignore-trailing-space': '⎵', 'ignore-space-change': '⎵⎵', 'ignore-all-space': '⌫', 'ignore-blank-lines': '□', 'multiple': '*'}
    EMOJI_DESCRIPTIONS = {'✓': 'Files are identical', '✗': 'Files differ (no single flag applies)', '←': 'File only in instance 1', '→': 'File only in instance 2', 'Aa': 'Differs only in case (--ignore-case)', '⇥': 'Differs in tab expansion (--ignore-tab-expansion)', '⎵': 'Differs in trailing space (--ignore-trailing-space)', '⎵⎵': 'Differs in space amounts (--ignore-space-change)', '⌫': 'Differs in all whitespace (--ignore-all-space)', '□': 'Differs in blank lines (--ignore-blank-lines)', '#': 'Differs in matching lines (--ignore-matching-lines)', '*': 'Multiple flags could apply'}

    @classmethod
    def analyze_difference(cls, file1: Path, file2: Path, ignore_matching_pattern: Optional[str]=None) -> Tuple[str, List[str]]:
        exists1 = file1.exists()
        exists2 = file2.exists()
        if not exists1 and (not exists2):
            return ('missing', [])
        if not exists1:
            return ('only2', [])
        if not exists2:
            return ('only1', [])
        if files_are_identical(file1, file2):
            return ('identical', [])
        applicable_flags = []
        for (flag_name, flag_option) in cls.FLAG_CONFIGS.items():
            if files_are_identical(file1, file2, flag_option):
                applicable_flags.append(flag_name)
        if ignore_matching_pattern:
            opts = DiffOptions(ignore_matching_lines=ignore_matching_pattern)
            if files_are_identical(file1, file2, opts):
                applicable_flags.append(f'ignore-matching-lines={ignore_matching_pattern}')
        if not applicable_flags:
            return ('different', [])
        elif len(applicable_flags) == 1:
            return (applicable_flags[0], applicable_flags)
        else:
            return ('multiple', applicable_flags)

    @classmethod
    def format_emoji_legend(cls) -> str:
        lines = []
        lines.append('EMOJI LEGEND')
        lines.append('=' * 70)
        status_emojis = [('✓', 'identical'), ('✗', 'different'), ('←', 'only1'), ('→', 'only2'), ('*', 'multiple')]
        flag_emojis = [('Aa', 'ignore-case'), ('⇥', 'ignore-tab-expansion'), ('⎵', 'ignore-trailing-space'), ('⎵⎵', 'ignore-space-change'), ('⌫', 'ignore-all-space'), ('□', 'ignore-blank-lines')]
        lines.append('File Status:')
        for (emoji, status_key) in status_emojis:
            desc = cls.EMOJI_DESCRIPTIONS.get(emoji, status_key)
            lines.append(f'  {emoji:4} {desc}')
        lines.append('')
        lines.append('Diff Flags (single flag would make files identical):')
        for (emoji, flag_key) in flag_emojis:
            desc = cls.EMOJI_DESCRIPTIONS.get(emoji, flag_key)
            lines.append(f'  {emoji:4} {desc}')
        lines.append('')
        lines.append("Note: '#' appears for files matching --ignore-matching-lines pattern")
        lines.append('=' * 70)
        lines.append('')
        return '\n'.join(lines)

    @classmethod
    def format_status_report(cls, file_statuses: Dict[str, Tuple[str, List[str]]], show_identical: bool=False, use_emoji: bool=False) -> str:
        if not file_statuses:
            return 'No files to compare\n'
        if not show_identical:
            file_statuses = {path: status for (path, status) in file_statuses.items() if status[0] != 'identical'}
        if not file_statuses:
            return 'All files are identical\n'
        lines = []
        if use_emoji:
            lines.append(cls.format_emoji_legend())
        max_path_len = max((len(path) for path in file_statuses.keys()))
        max_path_len = max(max_path_len, len('FILE'))
        path_width = min(max_path_len + 2, 80)
        if use_emoji:
            max_status_len = 4
        else:
            max_status_len = max((len(status[0]) for status in file_statuses.values()))
            max_status_len = max(max_status_len, len('STATUS'))
        status_width = max_status_len + 2
        header = f"{'FILE':<{path_width}} {'STATUS':<{status_width}} APPLICABLE FLAGS"
        lines.append(header)
        lines.append('=' * len(header))
        status_order = {'only1': 0, 'only2': 1, 'different': 2, 'multiple': 3, 'identical': 4}
        sorted_files = sorted(file_statuses.items(), key=lambda x: (status_order.get(x[1][0], 99), x[0]))
        for (path, (status, flags)) in sorted_files:
            display_path = path if len(path) <= path_width else '...' + path[-(path_width - 3):]
            if use_emoji:
                display_status = cls.STATUS_EMOJIS.get(status, status)
                if status.startswith('ignore-matching-lines'):
                    display_status = '#'
            else:
                display_status = status
            if status in ('only1', 'only2', 'identical', 'different'):
                lines.append(f'{display_path:<{path_width}} {display_status:<{status_width}} -')
            elif status == 'multiple':
                if use_emoji:
                    flag_emojis = []
                    for flag in flags:
                        if flag.startswith('ignore-matching-lines'):
                            flag_emojis.append('#')
                        else:
                            flag_emojis.append(cls.STATUS_EMOJIS.get(flag, flag))
                    flags_str = ', '.join(flag_emojis)
                else:
                    flags_str = ', '.join(flags)
                lines.append(f'{display_path:<{path_width}} {display_status:<{status_width}} {flags_str}')
            else:
                if use_emoji:
                    flags_str = display_status
                else:
                    flags_str = status
                lines.append(f'{display_path:<{path_width}} {display_status:<{status_width}} {flags_str}')
        lines.append('=' * len(header))
        status_counts = {}
        for (status, _) in file_statuses.values():
            status_counts[status] = status_counts.get(status, 0) + 1
        summary_parts = []
        for status in ['only1', 'only2', 'identical', 'different', 'multiple']:
            if status in status_counts:
                summary_parts.append(f'{status}: {status_counts[status]}')
        single_flag_counts = {}
        for (status, flags) in file_statuses.values():
            if status not in ('only1', 'only2', 'identical', 'different', 'multiple'):
                single_flag_counts[status] = single_flag_counts.get(status, 0) + 1
        for (flag, count) in sorted(single_flag_counts.items()):
            summary_parts.append(f'{flag}: {count}')
        lines.append('SUMMARY: ' + ', '.join(summary_parts))
        lines.append('')
        return '\n'.join(lines)

def get_fcl_files(run_dir: Path) -> Dict[str, Path]:
    fcl_files = {}
    for fcl_file in run_dir.rglob('*.fcl'):
        filename = fcl_file.name
        fcl_files[filename] = fcl_file
    return fcl_files

def run_fhicl_dump(fcl_file: Path, fhicl_file_path: Optional[Path]=None) -> Tuple[bool, str]:
    project_root = Path(__file__).parent.parent.parent
    fhicl_dump_bin = project_root / 'lib' / 'fhicl-dump'
    if not fhicl_dump_bin.exists():
        try:
            result = subprocess.run(['which', 'fhicl-dump'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                fhicl_dump_bin = Path(result.stdout.strip())
            else:
                return (False, 'fhicl-dump binary not found')
        except Exception as e:
            return (False, f'Failed to locate fhicl-dump: {e}')
    env = os.environ.copy()
    lib_dir = project_root / 'lib'
    if lib_dir.exists():
        ld_library_path = env.get('LD_LIBRARY_PATH', '')
        if ld_library_path:
            env['LD_LIBRARY_PATH'] = f'{lib_dir}:{ld_library_path}'
        else:
            env['LD_LIBRARY_PATH'] = str(lib_dir)
    if fhicl_file_path is None:
        fhicl_file_path = fcl_file.parent
    env['FHICL_FILE_PATH'] = str(fhicl_file_path)
    try:
        result = subprocess.run([str(fhicl_dump_bin), '-c', str(fcl_file)], capture_output=True, text=True, env=env, timeout=30)
        if result.returncode == 0:
            return (True, result.stdout)
        else:
            return (False, f'fhicl-dump failed: {result.stderr}')
    except subprocess.TimeoutExpired:
        return (False, 'fhicl-dump timeout')
    except Exception as e:
        return (False, f'fhicl-dump error: {e}')

def compare_files_with_fhicl_dump(file1: Path, file2: Path, fhicl_file_path: Optional[Path]=None) -> Tuple[bool, Optional[str]]:
    (success1, output1) = run_fhicl_dump(file1, fhicl_file_path)
    if not success1:
        return (False, f'Failed to process {file1.name}: {output1}')
    (success2, output2) = run_fhicl_dump(file2, fhicl_file_path)
    if not success2:
        return (False, f'Failed to process {file2.name}: {output2}')
    lines1 = [l for l in output1.splitlines() if not l.startswith('# Produced from') and (not l.startswith('#   Input'))]
    lines2 = [l for l in output2.splitlines() if not l.startswith('# Produced from') and (not l.startswith('#   Input'))]
    if lines1 == lines2:
        return (True, None)
    else:
        return (False, None)

def print_comparison_summary(results: Dict[str, any], instance1_name: str='Instance 1', instance2_name: str='Instance 2') -> None:
    logger.info('=' * 80)
    logger.info('Comparison Summary')
    logger.info('=' * 80)
    identical = len(results['identical_runs'])
    different = len(results['different_runs'])
    failed = len(results['failed_runs'])
    total = identical + different + failed
    logger.info('Total runs compared: %d', total)
    logger.info('Identical runs: %d (%.1f%%)', identical, 100 * identical / total if total > 0 else 0)
    logger.info('Different runs: %d (%.1f%%)', different, 100 * different / total if total > 0 else 0)
    logger.info('Failed runs: %d (%.1f%%)', failed, 100 * failed / total if total > 0 else 0)
    only_in_1 = results.get('only_in_db1', results.get('only_in_instance1', []))
    only_in_2 = results.get('only_in_db2', results.get('only_in_instance2', []))
    if only_in_1:
        logger.info('')
        logger.info('Runs only in %s: %d', instance1_name, len(only_in_1))
        logger.info('  %s', only_in_1)
    if only_in_2:
        logger.info('')
        logger.info('Runs only in %s: %d', instance2_name, len(only_in_2))
        logger.info('  %s', only_in_2)
    if results['different_runs']:
        logger.info('')
        logger.info('Runs with differences:')
        for (run_number, diffs) in sorted(results['different_runs'].items()):
            logger.info('  Run %d:', run_number)
            for diff in diffs:
                if '\n' in diff:
                    logger.info('    %s', diff.replace('\n', '\n    '))
                else:
                    logger.info('    - %s', diff)
    if results['failed_runs']:
        logger.info('')
        logger.info('Failed runs:')
        for (run_number, error) in sorted(results['failed_runs'].items()):
            logger.info('  Run %d: %s', run_number, error)
    logger.info('=' * 80)