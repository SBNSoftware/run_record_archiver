from __future__ import annotations
import argparse
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'tools'))
lib_dir = PROJECT_ROOT / 'lib'
os.environ['PYTHONPATH'] = f"{lib_dir}:{os.environ.get('PYTHONPATH', '')}"
os.environ['LD_LIBRARY_PATH'] = f"{lib_dir}:{os.environ.get('LD_LIBRARY_PATH', '')}"
os.environ['PATH'] = f"{lib_dir}:{os.environ.get('PATH', '')}"
from lib.comparison_utils import DiffAnalyzer, DiffOptions, compute_file_hash, files_are_identical, get_fcl_files, compare_files_with_fhicl_dump
from run_record_archiver.clients.artdaq import ArtdaqDBClient
from run_record_archiver.clients.ucondb import UconDBClient
from run_record_archiver.config import Config
from run_record_archiver.services.blob_creator import BlobCreator
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

class ArtdaqDBUconDBComparator:

    def __init__(self, config: Config, artdaqdb_output_dir: Path, ucondb_output_dir: Path, diff_options: Optional[DiffOptions]=None, use_fhicl_dump: bool=False, show_diff: bool=False, ignore_files: Optional[Set[str]]=None):
        self.config = config
        self.artdaqdb_output_dir = artdaqdb_output_dir
        self.ucondb_output_dir = ucondb_output_dir
        self.diff_options = diff_options or DiffOptions()
        self.use_fhicl_dump = use_fhicl_dump
        self.show_diff = show_diff
        self.ignore_files = ignore_files or set()
        logger.info(f'Initializing ArtdaqDB client: {config.artdaq_db.database_uri}')
        self.artdaqdb_client = ArtdaqDBClient(database_uri=config.artdaq_db.database_uri, use_tools=config.artdaq_db.use_tools, remote_host=config.artdaq_db.remote_host)
        logger.info(f'Initializing UconDB client: {config.ucon_db.server_url}')
        self.ucondb_client = UconDBClient(config=config.ucon_db)
        self.blob_creator = BlobCreator()
        self.results = {'matching': [], 'different': [], 'failed': [], 'missing_artdaqdb': [], 'missing_ucondb': []}

    def export_from_artdaqdb(self, run_number: int) -> Path:
        dest_dir = self.artdaqdb_output_dir / f'run_{run_number}'
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f'Exporting run {run_number} from ArtdaqDB')
        self.artdaqdb_client.export_run_configuration(run_number, dest_dir)
        logger.info(f'Exported run {run_number} from ArtdaqDB')
        return dest_dir

    def download_and_extract_ucondb(self, run_number: int) -> Path:
        dest_dir = self.ucondb_output_dir / f'run_{run_number}'
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f'Downloading run {run_number} from UconDB')
        blob = self.ucondb_client.get_data(run_number)
        extracted_files = self.blob_creator.extract_files_from_blob(blob, dest_dir)
        logger.info(f'Extracted {len(extracted_files)} files from UconDB run {run_number}')
        return dest_dir

    def should_ignore_file(self, filepath: str) -> bool:
        if not self.ignore_files:
            return False
        basename = Path(filepath).stem
        filename = Path(filepath).name
        return basename in self.ignore_files or filename in self.ignore_files

    def compare_run(self, run_number: int) -> Dict:
        result = {'run_number': run_number, 'status': 'unknown', 'differences': [], 'missing_in_ucondb': [], 'extra_in_ucondb': [], 'error': None}
        try:
            try:
                artdaqdb_dir = self.export_from_artdaqdb(run_number)
            except Exception as e:
                result['status'] = 'missing_artdaqdb'
                result['error'] = str(e)
                return result
            try:
                ucondb_dir = self.download_and_extract_ucondb(run_number)
            except Exception as e:
                result['status'] = 'missing_ucondb'
                result['error'] = str(e)
                return result
            artdaqdb_files = get_fcl_files(artdaqdb_dir)
            ucondb_files = get_fcl_files(ucondb_dir)
            if self.ignore_files:
                artdaqdb_files = {k: v for (k, v) in artdaqdb_files.items() if not self.should_ignore_file(k)}
                ucondb_files = {k: v for (k, v) in ucondb_files.items() if not self.should_ignore_file(k)}
            artdaqdb_set = set(artdaqdb_files.keys())
            ucondb_set = set(ucondb_files.keys())
            missing_in_ucondb = artdaqdb_set - ucondb_set
            extra_in_ucondb = ucondb_set - artdaqdb_set
            common_files = artdaqdb_set & ucondb_set
            if missing_in_ucondb:
                result['missing_in_ucondb'] = sorted(list(missing_in_ucondb))
            if extra_in_ucondb:
                result['extra_in_ucondb'] = sorted(list(extra_in_ucondb))
            for rel_path in sorted(common_files):
                artdaqdb_file = artdaqdb_files[rel_path]
                ucondb_file = ucondb_files[rel_path]
                if self.use_fhicl_dump:
                    (is_identical, diff) = compare_files_with_fhicl_dump(artdaqdb_file, ucondb_file, self.diff_options)
                else:
                    is_identical = files_are_identical(artdaqdb_file, ucondb_file, self.diff_options)
                    diff = None
                if not is_identical:
                    result['differences'].append({'file': rel_path, 'diff': diff if self.show_diff else None})
            if result['differences'] or missing_in_ucondb or extra_in_ucondb:
                result['status'] = 'different'
            else:
                result['status'] = 'matching'
        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)
            logger.error(f'Error comparing run {run_number}: {e}', exc_info=True)
        return result

    def compare_range(self, start: int, end: int) -> None:
        logger.info(f'Starting comparison for run range: {start} to {end}')
        total_runs = end - start + 1
        for (i, run_number) in enumerate(range(start, end + 1), 1):
            logger.info(f'[{i}/{total_runs}] Comparing run {run_number}...')
            result = self.compare_run(run_number)
            status = result['status']
            if status == 'matching':
                self.results['matching'].append(run_number)
                logger.info(f'  ✓ Run {run_number}: Files match (100% migration success)')
            elif status == 'different':
                self.results['different'].append(result)
                logger.error(f'  ✗ Run {run_number}: CRITICAL - Migration differences found!')
                if result['missing_in_ucondb']:
                    logger.error(f"    Missing in UconDB: {result['missing_in_ucondb']}")
                if result['extra_in_ucondb']:
                    logger.error(f"    Extra in UconDB: {result['extra_in_ucondb']}")
                if result['differences']:
                    logger.error(f"    Files with differences: {[d['file'] for d in result['differences']]}")
            elif status == 'missing_artdaqdb':
                self.results['missing_artdaqdb'].append(run_number)
                logger.warning(f'  ⊘ Run {run_number}: Missing in ArtdaqDB')
            elif status == 'missing_ucondb':
                self.results['missing_ucondb'].append(run_number)
                logger.warning(f'  ⊘ Run {run_number}: Missing in UconDB')
            else:
                self.results['failed'].append(result)
                logger.error(f"  ✗ Run {run_number}: Failed - {result['error']}")

    def print_summary(self) -> None:
        total = len(self.results['matching']) + len(self.results['different']) + len(self.results['failed'])
        print('\n' + '=' * 80)
        if self.results['different']:
            print('CRITICAL: MIGRATION VALIDATION FAILED')
            print('=' * 80)
        else:
            print('COMPARISON SUMMARY')
            print('=' * 80)
        print(f'Total runs compared: {total}')
        if total > 0:
            match_pct = 100.0 * len(self.results['matching']) / total
            diff_pct = 100.0 * len(self.results['different']) / total
            fail_pct = 100.0 * len(self.results['failed']) / total
            print(f"Matching runs: {len(self.results['matching'])} ({match_pct:.1f}%)")
            print(f"Different runs: {len(self.results['different'])} ({diff_pct:.1f}%)")
            print(f"Failed runs: {len(self.results['failed'])} ({fail_pct:.1f}%)")
        if self.results['missing_artdaqdb']:
            print(f"Missing in ArtdaqDB: {len(self.results['missing_artdaqdb'])}")
        if self.results['missing_ucondb']:
            print(f"Missing in UconDB: {len(self.results['missing_ucondb'])}")
        if self.results['different']:
            print('\nRuns with differences (MIGRATION BUGS):')
            for result in self.results['different']:
                run_num = result['run_number']
                print(f'  Run {run_num}:')
                if result['missing_in_ucondb']:
                    for fname in result['missing_in_ucondb']:
                        print(f'    - {fname}: Missing in UconDB')
                    print(f'      → Investigate partial migration failure!')
                if result['extra_in_ucondb']:
                    for fname in result['extra_in_ucondb']:
                        print(f'    - {fname}: Extra in UconDB (not in ArtdaqDB)')
                    print(f'      → Investigate blob packaging issue!')
                if result['differences']:
                    for diff in result['differences']:
                        fname = diff['file']
                        print(f'    - {fname}: Content mismatch')
                        print(f'      → Investigate BlobCreator or upload bug!')
                        if self.show_diff and diff['diff']:
                            print(f"\n{diff['diff']}\n")
        if self.results['failed']:
            print('\nFailed runs:')
            for result in self.results['failed']:
                run_num = result['run_number']
                error = result.get('error', 'Unknown error')
                print(f'  Run {run_num}: {error}')
        if not self.results['different'] and total > 0:
            print('\nAll runs match! Migration validation PASSED.')
        elif self.results['different']:
            print('\nIMMEDIATE ACTION REQUIRED: Investigate migration failures!')
        print('=' * 80)

def main():
    parser = argparse.ArgumentParser(description='Compare ArtdaqDB exports against UconDB archived blobs')
    parser.add_argument('config', nargs='?', default='config.yaml', help='Configuration file with both ArtdaqDB and UconDB settings (YAML format, default: config.yaml)')
    parser.add_argument('--start', type=int, required=True, help='Start run number (inclusive)')
    parser.add_argument('--end', type=int, required=True, help='End run number (inclusive)')
    parser.add_argument('--artdaqdb-dir', type=Path, default=Path('/tmp/export_artdaqdb1'), help='Output directory for ArtdaqDB exports (default: /tmp/export_artdaqdb1)')
    parser.add_argument('--ucondb-dir', type=Path, default=Path('/tmp/export_ucondb2'), help='Output directory for UconDB files (default: /tmp/export_ucondb2)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose (DEBUG) logging')
    parser.add_argument('--show-diff', action='store_true', help='Show detailed diffs for differences')
    parser.add_argument('--with-fhicl-dump', action='store_true', help='Use fhicl-dump to normalize files before comparison')
    parser.add_argument('--ignore-case', action='store_true', help='Ignore case differences')
    parser.add_argument('--ignore-all-space', action='store_true', help='Ignore all whitespace')
    parser.add_argument('--ignore-blank-lines', action='store_true', help='Ignore blank lines')
    parser.add_argument('--ignore-matching-lines', type=str, help='Ignore lines matching regex pattern')
    parser.add_argument('--ignore-files', type=str, help="Comma-separated list of file basenames to ignore (e.g., 'RunHistory2,settings')")
    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    config_path = Path(args.config)
    if not config_path.exists():
        logger.error(f'Configuration file not found: {config_path.absolute()}')
        logger.error('Please provide a valid configuration file:')
        logger.error(f'  - Create config.yaml in the current directory, or')
        logger.error(f'  - Specify a different config file as the first argument')
        logger.error(f'  - See config_template.yaml for an example')
        sys.exit(1)
    logger.info(f'Loading configuration from {args.config}')
    config = Config.from_file(args.config)
    diff_options = DiffOptions(ignore_case=args.ignore_case, ignore_all_space=args.ignore_all_space, ignore_blank_lines=args.ignore_blank_lines, ignore_matching_lines=args.ignore_matching_lines)
    ignore_files = set()
    if args.ignore_files:
        for filename in args.ignore_files.split(','):
            filename = filename.strip()
            if filename:
                ignore_files.add(filename)
                if not filename.endswith('.fcl'):
                    ignore_files.add(f'{filename}.fcl')
    comparator = ArtdaqDBUconDBComparator(config=config, artdaqdb_output_dir=args.artdaqdb_dir, ucondb_output_dir=args.ucondb_dir, diff_options=diff_options, use_fhicl_dump=args.with_fhicl_dump, show_diff=args.show_diff, ignore_files=ignore_files)
    try:
        comparator.compare_range(args.start, args.end)
    except KeyboardInterrupt:
        logger.warning('\nComparison interrupted by user')
        sys.exit(130)
    except Exception as e:
        logger.error(f'Comparison failed: {e}', exc_info=True)
        sys.exit(1)
    comparator.print_summary()
    if comparator.results['different'] or comparator.results['failed']:
        sys.exit(1)
    else:
        sys.exit(0)
if __name__ == '__main__':
    main()