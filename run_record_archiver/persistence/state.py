import json
import logging
from pathlib import Path
from typing import Any, Dict, List

def read_state(state_file: Path) -> Dict[str, Any]:
    try:
        if state_file.exists():
            with open(state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        logging.getLogger(__name__).warning('Failed to read state file %s: %s', state_file, e)
    return {}

def write_state(state_file: Path, state: Dict[str, Any]) -> bool:
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)
        return True
    except (IOError, TypeError) as e:
        logging.getLogger(__name__).error('Failed to write state file %s: %s', state_file, e)
        return False

def update_contiguous_run_state(state_file: Path, successful_runs: List[int]) -> None:
    if not successful_runs:
        return
    current_state = read_state(state_file)
    last_run = current_state.get('last_contiguous_run', 0)
    for run in sorted(successful_runs):
        if run == last_run + 1:
            last_run = run
        elif run > last_run + 1:
            break
    if last_run > current_state.get('last_contiguous_run', 0):
        current_state['last_contiguous_run'] = last_run
        write_state(state_file, current_state)
        logging.getLogger(__name__).info('Updated last contiguous run in %s to %d', state_file.name, last_run)

def update_attempted_run_state(state_file: Path, attempted_runs: List[int]) -> None:
    if not attempted_runs:
        return
    current_state = read_state(state_file)
    last_attempted = current_state.get('last_attempted_run', 0)
    new_last_attempted = max(max(attempted_runs), last_attempted)
    if new_last_attempted > last_attempted:
        current_state['last_attempted_run'] = new_last_attempted
        write_state(state_file, current_state)
        logging.getLogger(__name__).info('Updated last_attempted_run in %s: %d -> %d (processed %d runs: %d to %d)', state_file.name, last_attempted, new_last_attempted, len(attempted_runs), min(attempted_runs), max(attempted_runs))
    else:
        logging.getLogger(__name__).debug('No update needed for last_attempted_run in %s (current=%d, max_attempted=%d)', state_file.name, last_attempted, max(attempted_runs))

def get_incremental_start_run(state_file: Path) -> int:
    current_state = read_state(state_file)
    last_contiguous = current_state.get('last_contiguous_run', 0)
    last_attempted = current_state.get('last_attempted_run', 0)
    start_run = max(last_contiguous, last_attempted)
    logger = logging.getLogger(__name__)
    logger.debug('Incremental start run for %s: %d (last_contiguous=%d, last_attempted=%d)', state_file.name, start_run, last_contiguous, last_attempted)
    return start_run

def parse_run_records_from_file(run_records_file: Path) -> List[int]:
    if not run_records_file.exists():
        return []
    try:
        with open(run_records_file, 'r', encoding='utf-8') as f:
            return [int(line.strip()) for line in f if line.strip().isdigit()]
    except (IOError, ValueError) as e:
        logging.getLogger(__name__).error('Failed to parse run records file %s: %s', run_records_file, e)
        return []

def append_to_failure_log(failure_log: Path, failed_runs: List[int]):
    try:
        with failure_log.open('a', encoding='utf-8') as f:
            for run in sorted(failed_runs):
                f.write(f'{run}\n')
    except IOError as e:
        logging.getLogger(__name__).error('Could not write to failure log: %s', e)

def write_failure_log(failure_log: Path, failed_runs: List[int]):
    try:
        with failure_log.open('w', encoding='utf-8') as f:
            for run in sorted(failed_runs):
                f.write(f'{run}\n')
    except IOError as e:
        logging.getLogger(__name__).error('Could not update failure log: %s', e)