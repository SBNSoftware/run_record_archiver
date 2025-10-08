import logging
import os
import shlex
import subprocess
from pathlib import Path
from typing import Optional

from ..exceptions import ArtdaqDBError


def run_bulkloader(
    run_number: int,
    config_name: str,
    data_dir: Path,
    archive_uri: str,
    remote_host: Optional[str],
) -> None:
    logger = logging.getLogger(__name__)
    env_keys = [
        "PATH",
        "LD_LIBRARY_PATH",
        "PYTHONPATH",
        "ARTDAQ_DATABASE_DATADIR",
        "ARTDAQ_DATABASE_CONFDIR",
    ]
    set_env_parts = [
        f'export {k}="{os.environ[k]}"' for k in env_keys if k in os.environ
    ]
    set_env_parts.append(f'export ARTDAQ_DATABASE_URI="{archive_uri}"')
    set_env_command = "; ".join(set_env_parts)
    num_threads = "$(( $(nproc)/2 ))"

    if remote_host:
        sshopts = '-o "StrictHostKeyChecking=no" -o "UserKnownHostsFile=/dev/null" -o "BatchMode=yes"'
        remote_tmpdir = f"/tmp/bulkloader_{run_number}_{os.getpid()}"
        bulkloader_cmd = f"bulkloader -r {run_number} -c {shlex.quote(config_name)} -p {shlex.quote(remote_tmpdir)} -t {num_threads}"
        remote_script = f"mkdir -p {shlex.quote(remote_tmpdir)}; cd {shlex.quote(remote_tmpdir)}; tar xzf -; {set_env_command}; {bulkloader_cmd}; cd /; rm -rf {shlex.quote(remote_tmpdir)}"
        command_to_run = f"tar czf - -C {shlex.quote(str(data_dir))} . | ssh {sshopts} {shlex.quote(remote_host)} {shlex.quote(remote_script)}"
    else:
        bulkloader_cmd = f"bulkloader -r {run_number} -c {shlex.quote(config_name)} -p {shlex.quote(str(data_dir))} -t {num_threads}"
        command_to_run = (
            f"{set_env_command}; cd {shlex.quote(str(data_dir))}; {bulkloader_cmd}"
        )

    try:
        logger.debug("Executing bulkloader command: %s", command_to_run)
        result = subprocess.run(
            command_to_run,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
        logger.debug("Bulkloader stdout:\n%s", result.stdout)
        if result.stderr:
            logger.warning("Bulkloader stderr:\n%s", result.stderr)
    except subprocess.CalledProcessError as e:
        error_message = f"Bulkloader failed with code {e.returncode}.\nCmd: {e.cmd}\nStdout: {e.stdout}\nStderr: {e.stderr}"
        logger.error(error_message)
        raise ArtdaqDBError(error_message) from e
    except subprocess.TimeoutExpired as e:
        error_message = (
            f"Bulkloader timed out.\nStdout: {e.stdout}\nStderr: {e.stderr}"
        )
        logger.error(error_message)
        raise ArtdaqDBError(error_message) from e
