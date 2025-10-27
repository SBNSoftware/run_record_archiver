import logging
from pathlib import Path
from typing import List, Set, Tuple
from .clients.artdaq import ArtdaqDBClient
from .clients.ucondb import UconDBClient
from .config import Config
from .exceptions import ArchiverError
from .persistence import state

class Reporter:

    def __init__(self, config: Config, artdaq_client: ArtdaqDBClient, ucon_client: UconDBClient):
        self._config = config
        self._artdaq = artdaq_client
        self._ucon = ucon_client
        self._logger = logging.getLogger(__name__)

    def _get_filesystem_runs(self) -> Set[int]:
        self._logger.debug('Scanning filesystem: %s', self._config.source_files.run_records_dir)
        try:
            fs_runs = {int(p.name) for p in self._config.source_files.run_records_dir.iterdir() if p.is_dir() and p.name.isdigit()}
            self._logger.debug('Found %d runs in filesystem', len(fs_runs))
            return fs_runs
        except (IOError, PermissionError) as e:
            raise ArchiverError(f'Cannot read run records directory: {e}', stage='Reporter', context={'directory': str(self._config.source_files.run_records_dir)}) from e

    def _compute_ranges_and_gaps(self, runs: Set[int]) -> Tuple[List[Tuple[int, int]], List[int]]:
        if not runs:
            return ([], [])
        sorted_runs = sorted(runs)
        min_run = sorted_runs[0]
        max_run = sorted_runs[-1]
        full_range = set(range(min_run, max_run + 1))
        gaps = sorted(list(full_range - runs))
        ranges = []
        range_start = sorted_runs[0]
        prev_run = sorted_runs[0]
        for run in sorted_runs[1:]:
            if run != prev_run + 1:
                ranges.append((range_start, prev_run))
                range_start = run
            prev_run = run
        ranges.append((range_start, prev_run))
        return (ranges, gaps)

    def _format_ranges(self, ranges: List[Tuple[int, int]], max_display: int=10) -> str:
        if not ranges:
            return 'None'
        if len(ranges) <= max_display:
            return ', '.join((f'{start}-{end}' if start != end else str(start) for (start, end) in ranges))
        else:
            display_count = max_display // 2
            first_ranges = ranges[:display_count]
            last_ranges = ranges[-display_count:]
            first_str = ', '.join((f'{start}-{end}' if start != end else str(start) for (start, end) in first_ranges))
            last_str = ', '.join((f'{start}-{end}' if start != end else str(start) for (start, end) in last_ranges))
            return f'{first_str} ... {last_str} ({len(ranges)} ranges total)'

    def _format_gaps(self, gaps: List[int], max_display: int=20) -> str:
        if not gaps:
            return 'None'
        if len(gaps) <= max_display:
            return ', '.join((str(g) for g in gaps))
        else:
            displayed = gaps[:max_display]
            return f"{', '.join((str(g) for g in displayed))} ... ({len(gaps)} gaps total)"

    def _get_recommendations(self, fs_runs: Set[int], artdaq_runs: Set[int], ucon_runs: Set[int]) -> List[str]:
        recommendations = []
        runs_to_import = fs_runs - artdaq_runs
        if runs_to_import:
            count = len(runs_to_import)
            min_run = min(runs_to_import)
            max_run = max(runs_to_import)
            recommendations.append(f'Run IMPORTER: {count} run(s) on filesystem not in artdaqDB (range: {min_run}-{max_run})')
        runs_to_migrate = artdaq_runs - ucon_runs
        if runs_to_migrate:
            count = len(runs_to_migrate)
            min_run = min(runs_to_migrate)
            max_run = max(runs_to_migrate)
            recommendations.append(f'Run MIGRATOR: {count} run(s) in artdaqDB not in UconDB (range: {min_run}-{max_run})')
        orphaned = artdaq_runs - fs_runs
        if orphaned:
            count = len(orphaned)
            recommendations.append(f'WARNING: {count} run(s) in artdaqDB but not on filesystem (may have been deleted)')
        ucon_only = ucon_runs - artdaq_runs
        if ucon_only:
            count = len(ucon_only)
            recommendations.append(f'INFO: {count} run(s) in UconDB but not in artdaqDB (may have been cleaned up from intermediate storage)')
        if not recommendations:
            recommendations.append('All systems are synchronized - no action needed')
        return recommendations

    def _get_state_info(self) -> dict:
        import_state = state.read_state(self._config.app.import_state_file)
        migrate_state = state.read_state(self._config.app.migrate_state_file)
        import_failures = state.parse_run_records_from_file(self._config.app.import_failure_log)
        migrate_failures = state.parse_run_records_from_file(self._config.app.migrate_failure_log)
        return {'import_last_contiguous': import_state.get('last_contiguous_run', 0), 'migrate_last_contiguous': migrate_state.get('last_contiguous_run', 0), 'import_failures': set(import_failures), 'migrate_failures': set(migrate_failures)}

    def _compare_with_state(self, fs_runs: Set[int], artdaq_runs: Set[int], ucon_runs: Set[int], state_info: dict) -> None:
        self._logger.info('')
        self._logger.info('=' * 70)
        self._logger.info('STATE COMPARISON')
        self._logger.info('=' * 70)
        import_last = state_info['import_last_contiguous']
        self._logger.info('')
        self._logger.info('IMPORT STAGE STATE')
        self._logger.info('-' * 70)
        self._logger.info('  Last Contiguous Run: %d', import_last)
        if import_last > 0:
            expected_in_artdaq = {r for r in fs_runs if r <= import_last}
            missing_from_artdaq = expected_in_artdaq - artdaq_runs
            if missing_from_artdaq:
                self._logger.warning('  Missing in ArtdaqDB:  %d run(s) before last contiguous (%s)', len(missing_from_artdaq), self._format_gaps(sorted(list(missing_from_artdaq)), max_display=10))
            else:
                self._logger.info('  Status:              All expected runs present in ArtdaqDB')
            new_runs = {r for r in fs_runs if r > import_last}
            if new_runs:
                min_new = min(new_runs)
                max_new = max(new_runs)
                self._logger.info('  New Runs Available:  %d run(s) since last state update (range: %d-%d)', len(new_runs), min_new, max_new)
        else:
            self._logger.info('  Status:              No import state recorded')
        if state_info['import_failures']:
            self._logger.warning('  Failed Runs:         %d run(s) logged as failed (%s)', len(state_info['import_failures']), self._format_gaps(sorted(list(state_info['import_failures'])), max_display=10))
        migrate_last = state_info['migrate_last_contiguous']
        self._logger.info('')
        self._logger.info('MIGRATION STAGE STATE')
        self._logger.info('-' * 70)
        self._logger.info('  Last Contiguous Run: %d', migrate_last)
        if migrate_last > 0:
            expected_in_ucon = {r for r in artdaq_runs if r <= migrate_last}
            missing_from_ucon = expected_in_ucon - ucon_runs
            if missing_from_ucon:
                self._logger.warning('  Missing in UconDB:   %d run(s) before last contiguous (%s)', len(missing_from_ucon), self._format_gaps(sorted(list(missing_from_ucon)), max_display=10))
            else:
                self._logger.info('  Status:              All expected runs present in UconDB')
            new_runs = {r for r in artdaq_runs if r > migrate_last}
            if new_runs:
                min_new = min(new_runs)
                max_new = max(new_runs)
                self._logger.info('  New Runs Available:  %d run(s) since last state update (range: %d-%d)', len(new_runs), min_new, max_new)
        else:
            self._logger.info('  Status:              No migration state recorded')
        if state_info['migrate_failures']:
            self._logger.warning('  Failed Runs:         %d run(s) logged as failed (%s)', len(state_info['migrate_failures']), self._format_gaps(sorted(list(state_info['migrate_failures'])), max_display=10))

    def generate_report(self, compare_state: bool=False) -> None:
        self._logger.info('=' * 70)
        self._logger.info('RUN RECORD ARCHIVER - STATUS REPORT')
        self._logger.info('=' * 70)
        self._logger.info('Querying data sources...')
        try:
            fs_runs = self._get_filesystem_runs()
            self._logger.info('✓ Filesystem query complete')
        except ArchiverError as e:
            self._logger.error('✗ Filesystem query failed: %s', e)
            return
        try:
            artdaq_runs = self._artdaq.get_archived_runs()
            self._logger.info('✓ ArtdaqDB query complete')
        except ArchiverError as e:
            self._logger.error('✗ ArtdaqDB query failed: %s', e)
            return
        try:
            ucon_runs = self._ucon.get_existing_runs()
            self._logger.info('✓ UconDB query complete')
        except ArchiverError as e:
            self._logger.error('✗ UconDB query failed: %s', e)
            return
        (fs_ranges, fs_gaps) = self._compute_ranges_and_gaps(fs_runs)
        (artdaq_ranges, artdaq_gaps) = self._compute_ranges_and_gaps(artdaq_runs)
        (ucon_ranges, ucon_gaps) = self._compute_ranges_and_gaps(ucon_runs)
        self._logger.info('')
        self._logger.info('=' * 70)
        self._logger.info('DATA SOURCE SUMMARY')
        self._logger.info('=' * 70)
        self._logger.info('')
        self._logger.info('FILESYSTEM (Source)')
        self._logger.info('-' * 70)
        self._logger.info('  Location:        %s', self._config.source_files.run_records_dir)
        self._logger.info('  Total Runs:      %d', len(fs_runs))
        if fs_runs:
            self._logger.info('  Range:           %d to %d', min(fs_runs), max(fs_runs))
            self._logger.info('  Contiguous:      %s', self._format_ranges(fs_ranges))
            self._logger.info('  Gaps:            %s', self._format_gaps(fs_gaps))
        else:
            self._logger.info('  Status:          No runs found')
        self._logger.info('')
        self._logger.info('ARTDAQDB (Intermediate Storage)')
        self._logger.info('-' * 70)
        self._logger.info('  Database URI:    %s', self._config.artdaq_db.database_uri)
        self._logger.info('  Total Runs:      %d', len(artdaq_runs))
        if artdaq_runs:
            self._logger.info('  Range:           %d to %d', min(artdaq_runs), max(artdaq_runs))
            self._logger.info('  Contiguous:      %s', self._format_ranges(artdaq_ranges))
            self._logger.info('  Gaps:            %s', self._format_gaps(artdaq_gaps))
        else:
            self._logger.info('  Status:          No runs found')
        self._logger.info('')
        self._logger.info('UCONDB (Long-term Storage)')
        self._logger.info('-' * 70)
        self._logger.info('  Server URL:      %s', self._config.ucon_db.server_url)
        self._logger.info('  Folder/Object:   %s/%s', self._config.ucon_db.folder_name, self._config.ucon_db.object_name)
        self._logger.info('  Total Runs:      %d', len(ucon_runs))
        if ucon_runs:
            self._logger.info('  Range:           %d to %d', min(ucon_runs), max(ucon_runs))
            self._logger.info('  Contiguous:      %s', self._format_ranges(ucon_ranges))
            self._logger.info('  Gaps:            %s', self._format_gaps(ucon_gaps))
        else:
            self._logger.info('  Status:          No runs found')
        if compare_state:
            state_info = self._get_state_info()
            self._compare_with_state(fs_runs, artdaq_runs, ucon_runs, state_info)
        recommendations = self._get_recommendations(fs_runs, artdaq_runs, ucon_runs)
        self._logger.info('')
        self._logger.info('=' * 70)
        self._logger.info('RECOMMENDATIONS')
        self._logger.info('=' * 70)
        for (i, rec) in enumerate(recommendations, 1):
            self._logger.info('%d. %s', i, rec)
        self._logger.info('')
        self._logger.info('=' * 70)
        self._logger.info('END OF STATUS REPORT')
        self._logger.info('=' * 70)