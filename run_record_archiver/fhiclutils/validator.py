import os
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple, Optional

def validate_fhicl(content: Optional[str]=None, file_path: Optional[Path]=None, fhicl_dump_path: str='fhicl-dump') -> Tuple[bool, str]:
    if content is None and file_path is None:
        raise ValueError('Either content or file_path must be provided')
    if not Path(fhicl_dump_path).exists():
        raise FileNotFoundError(f'fhicl-dump not found. Expected at: {fhicl_dump_path}\nMake sure fhicl-dump is in PATH or lib directory')
    temp_file = None
    try:
        if content is not None:
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.fcl', delete=False, encoding='utf-8')
            temp_file.write(content)
            temp_file.close()
            validate_path = Path(temp_file.name)
        else:
            validate_path = file_path
        if not validate_path.exists():
            return (False, f'File not found: {validate_path}')
        env = os.environ.copy()
        env['FHICL_FILE_PATH'] = str(validate_path.parent)
        result = subprocess.run([fhicl_dump_path, '--quiet', str(validate_path)], capture_output=True, text=True, env=env, timeout=10)
        if result.returncode == 0:
            return (True, 'Valid FHiCL')
        else:
            error_msg = result.stderr.strip() if result.stderr else 'Unknown error'
            if not error_msg and result.stdout:
                error_msg = result.stdout.strip()
            return (False, f'FHiCL validation failed:\n{error_msg}')
    except subprocess.TimeoutExpired:
        return (False, 'FHiCL validation timed out (>10s)')
    except Exception as e:
        return (False, f'FHiCL validation error: {e}')
    finally:
        if temp_file is not None:
            try:
                os.unlink(temp_file.name)
            except OSError:
                pass

def validate_fhicl_file(file_path: Path, fhicl_dump_path: str='fhicl-dump') -> Tuple[bool, str]:
    return validate_fhicl(file_path=file_path, fhicl_dump_path=fhicl_dump_path)

def validate_fhicl_content(content: str, fhicl_dump_path: str='fhicl-dump') -> Tuple[bool, str]:
    return validate_fhicl(content=content, fhicl_dump_path=fhicl_dump_path)