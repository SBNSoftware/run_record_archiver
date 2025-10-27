import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union
import yaml
from .exceptions import ConfigurationError

class ConfigExpander:
    ENV_VAR_PATTERN = re.compile('\\$\\{([A-Z][A-Z0-9_]*)(:-([^}]*))?\\}')
    PARAM_REF_PATTERN = re.compile('\\$\\{([a-z_][a-z0-9_]*(?:\\.[a-z_][a-z0-9_]*)*)\\}')

    @classmethod
    def expand_config(cls, config_data: Dict[str, Any]) -> Dict[str, Any]:
        config_data = cls._expand_env_vars_recursive(config_data)
        config_data = cls._expand_param_refs(config_data)
        return config_data

    @classmethod
    def _expand_env_vars_recursive(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: cls._expand_env_vars_recursive(v) for (k, v) in data.items()}
        elif isinstance(data, list):
            return [cls._expand_env_vars_recursive(item) for item in data]
        elif isinstance(data, str):
            return cls._expand_env_vars(data)
        else:
            return data

    @classmethod
    def _expand_env_vars(cls, value: str) -> str:

        def find_matching_brace(s, start):
            count = 1
            i = start + 1
            while i < len(s) and count > 0:
                if s[i:i + 2] == '${':
                    count += 1
                    i += 2
                elif s[i] == '}':
                    count -= 1
                    i += 1
                else:
                    i += 1
            return i - 1 if count == 0 else -1
        max_iterations = 10
        for _ in range(max_iterations):
            changed = False
            result = []
            i = 0
            while i < len(value):
                if value[i:i + 2] == '${':
                    close_idx = find_matching_brace(value, i + 1)
                    if close_idx > 0:
                        content = value[i + 2:close_idx]
                        if content and content[0].isupper():
                            if ':-' in content:
                                (var_name, default_value) = content.split(':-', 1)
                                if '${' in default_value:
                                    default_value = cls._expand_env_vars(default_value)
                                expanded = os.environ.get(var_name, default_value)
                            else:
                                expanded = os.environ.get(content, '')
                            result.append(expanded)
                            i = close_idx + 1
                            changed = True
                        else:
                            result.append(value[i:close_idx + 1])
                            i = close_idx + 1
                    else:
                        result.append(value[i])
                        i += 1
                else:
                    result.append(value[i])
                    i += 1
            value = ''.join(result)
            if not changed:
                break
        return value

    @classmethod
    def _expand_param_refs(cls, config_data: Dict[str, Any]) -> Dict[str, Any]:
        result = config_data.copy()
        max_passes = 5
        for pass_num in range(max_passes):
            changed = False
            flat_params = cls._flatten_config(result)
            expanding: Set[str] = set()

            def expand_value(value: Any, current_section: str) -> Any:
                nonlocal changed
                if isinstance(value, dict):
                    return {k: expand_value(v, current_section) for (k, v) in value.items()}
                elif isinstance(value, list):
                    return [expand_value(item, current_section) for item in value]
                elif isinstance(value, str):
                    expanded = cls._expand_param_refs_in_string(value, current_section, flat_params, expanding)
                    if expanded != value:
                        changed = True
                    return expanded
                else:
                    return value
            new_result = {}
            for (section_name, section_data) in result.items():
                if isinstance(section_data, dict):
                    new_result[section_name] = expand_value(section_data, section_name)
                else:
                    new_result[section_name] = section_data
            result = new_result
            if not changed:
                break
        return result

    @classmethod
    def _flatten_config(cls, config_data: Dict[str, Any]) -> Dict[str, Any]:
        flat = {}
        for (section_name, section_data) in config_data.items():
            if isinstance(section_data, dict):
                for (param_name, param_value) in section_data.items():
                    flat[f'{section_name}.{param_name}'] = param_value
        return flat

    @classmethod
    def _expand_param_refs_in_string(cls, value: str, current_section: str, flat_params: Dict[str, Any], expanding: Set[str]) -> str:
        PARAM_REF_WITH_DEFAULT = re.compile('\\$\\{([a-z_][a-z0-9_]*(?:\\.[a-z_][a-z0-9_]*)*)(:-([^}]*))?\\}')

        def replacer(match):
            ref = match.group(1)
            default_value = match.group(3) if match.group(3) is not None else None
            if '.' not in ref:
                full_ref = f'{current_section}.{ref}'
            else:
                full_ref = ref
            if full_ref in expanding:
                raise ConfigurationError(f'Circular reference detected: {full_ref}')
            if full_ref in flat_params:
                ref_value = flat_params[full_ref]
                if isinstance(ref_value, str) and '${' in ref_value:
                    expanding.add(full_ref)
                    try:
                        ref_section = full_ref.split('.')[0]
                        ref_value = cls._expand_param_refs_in_string(ref_value, ref_section, flat_params, expanding)
                    finally:
                        expanding.remove(full_ref)
                return str(ref_value)
            elif default_value is not None:
                return default_value
            else:
                return match.group(0)
        max_iterations = 10
        for _ in range(max_iterations):
            new_value = PARAM_REF_WITH_DEFAULT.sub(replacer, value)
            if new_value == value:
                break
            value = new_value
        return value

class AppConfig:

    def __init__(self, data: Dict[str, Any]):
        self.work_dir = Path(data.get('work_dir', '/tmp/run_record_archiver'))
        self.import_state_file = Path(data.get('import_state_file', f'{self.work_dir}/importer_state.json'))
        self.import_failure_log = Path(data.get('import_failure_log', f'{self.work_dir}/import_failures.log'))
        self.migrate_state_file = Path(data.get('migrate_state_file', f'{self.work_dir}/migrator_state.json'))
        self.migrate_failure_log = Path(data.get('migrate_failure_log', f'{self.work_dir}/migrate_failures.log'))
        self.lock_file = Path(data.get('lock_file', f'{self.work_dir}/.archiver.lock'))
        self.batch_size = int(data.get('batch_size', 5))
        self.parallel_workers = int(data.get('parallel_workers', 2))
        self.run_process_retries = int(data.get('run_process_retries', 2))
        self.retry_delay_seconds = int(data.get('retry_delay_seconds', 3))
        self.log_level = str(data.get('log_level', 'INFO')).upper()
        log_file_path = data.get('log_file')
        self.log_file: Optional[Path] = Path(log_file_path) if log_file_path else None

class AppFuzzConfig:

    def __init__(self, data: Dict[str, Any]):
        self.random_skip_percent = int(data.get('random_skip_percent', 0))
        self.random_skip_retry = bool(data.get('random_skip_retry', False))
        self.random_error_percent = int(data.get('random_error_percent', 0))
        self.random_error_retry = bool(data.get('random_error_retry', False))

class SourceFilesConfig:

    def __init__(self, data: Dict[str, Any]):
        try:
            self.run_records_dir = Path(data['run_records_dir'])
        except KeyError as e:
            raise ConfigurationError("Source files config missing required key: 'run_records_dir'") from e

class ArtdaqDBConfig:

    def __init__(self, data: Dict[str, Any]):
        self.use_tools = bool(data.get('use_tools', False))
        self.remote_host: Optional[str] = data.get('remote_host')
        try:
            self.database_uri = str(data['database_uri'])
            self.fcl_conf_dir = Path(data['fcl_conf_dir'])
        except KeyError as e:
            raise ConfigurationError(f"ArtdaqDB config missing required key: '{e.args[0]}'") from e

class UconDBConfig:

    def __init__(self, data: Dict[str, Any]):
        self.timeout_seconds = int(data.get('timeout_seconds', 10))
        try:
            self.server_url = str(data['server_url'])
            self.folder_name = str(data['folder_name'])
            self.object_name = str(data['object_name'])
            self.writer_user = str(data['writer_user'])
            self.writer_password = str(data['writer_password'])
        except KeyError as e:
            raise ConfigurationError(f"UconDB config missing required key: '{e.args[0]}'") from e

class EmailConfig:

    def __init__(self, data: Dict[str, Any]):
        self.enabled = bool(data.get('enabled', False))
        self.recipient_email: Optional[str] = data.get('recipient_email', 'user@example.com' if not self.enabled else None)
        self.sender_email: Optional[str] = data.get('sender_email', 'archiver@example.com' if not self.enabled else None)
        self.smtp_host: Optional[str] = data.get('smtp_host', 'smtp.example.com' if not self.enabled else None)
        self.smtp_port = int(data.get('smtp_port', 25))
        self.smtp_use_tls = bool(data.get('smtp_use_tls', False))
        self.smtp_user: Optional[str] = data.get('smtp_user')
        self.smtp_password: Optional[str] = data.get('smtp_password')
        if self.enabled and (not all([self.recipient_email, self.sender_email, self.smtp_host])):
            raise ConfigurationError("Email config: 'recipient_email', 'sender_email', and 'smtp_host' are required when enabled is true.")

class SlackConfig:

    def __init__(self, data: Dict[str, Any]):
        self.enabled = bool(data.get('enabled', False))
        self.bot_token: Optional[str] = data.get('bot_token')
        self.channel: Optional[str] = data.get('channel')
        self.mention_users: Optional[str] = data.get('mention_users')
        if self.enabled and (not all([self.bot_token, self.channel])):
            raise ConfigurationError("Slack config: 'bot_token' and 'channel' are required when enabled is true.")

class ReportingConfig:

    def __init__(self, data: Dict[str, Any]):
        self.email = EmailConfig(data.get('email', {}))
        self.slack = SlackConfig(data.get('slack', {}))
        if 'send_email_on_error' in data:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("DEPRECATED: Top-level email config in 'reporting' section is deprecated. Please move email settings to 'reporting.email' section.")
            if not data.get('email'):
                legacy_email_data = {'enabled': data.get('send_email_on_error', False), 'recipient_email': data.get('recipient_email'), 'sender_email': data.get('sender_email'), 'smtp_host': data.get('smtp_host'), 'smtp_port': data.get('smtp_port', 587), 'smtp_use_tls': data.get('smtp_use_tls', True), 'smtp_user': data.get('smtp_user'), 'smtp_password': data.get('smtp_password')}
                self.email = EmailConfig(legacy_email_data)

class CarbonConfig:

    def __init__(self, data: Dict[str, Any]):
        self.enabled = bool(data.get('enabled', False))
        self.host: Optional[str] = data.get('host')
        self.port = int(data.get('port', 2003))
        self.metric_prefix: Optional[str] = data.get('metric_prefix')
        if self.enabled and (not all([self.host, self.metric_prefix])):
            raise ConfigurationError("Carbon config: 'host' and 'metric_prefix' are required when enabled.")

class FhiclizeGenerateConfig:
    KNOWN_CONVERTERS = {'boot', 'metadata', 'known_boardreaders_list', 'settings', 'setup', 'environment', 'ranks'}
    KNOWN_GENERATORS = {'RunHistory', 'RunHistory2'}

    def __init__(self, data: Union[List[str], Dict[str, Any], None]):
        if data is None:
            self.file_list = list(self.KNOWN_CONVERTERS | self.KNOWN_GENERATORS)
        elif isinstance(data, list):
            self.file_list = [self._normalize_filename(f) for f in data]
        elif isinstance(data, dict):
            files = data.get('files', [])
            self.file_list = [self._normalize_filename(f) for f in files]
        else:
            raise ConfigurationError(f'Invalid fhiclize_generate config type: {type(data)}. Expected list, dict, or None.')
        unknown_files = set(self.file_list) - (self.KNOWN_CONVERTERS | self.KNOWN_GENERATORS)
        if unknown_files:
            raise ConfigurationError(f'Unknown file types in fhiclize_generate: {unknown_files}. Known converters: {self.KNOWN_CONVERTERS}. Known generators: {self.KNOWN_GENERATORS}.')
        self.converters = set(self.file_list) & self.KNOWN_CONVERTERS
        self.generators = set(self.file_list) & self.KNOWN_GENERATORS

    @staticmethod
    def _normalize_filename(filename: str) -> str:
        if filename.endswith('.txt') or filename.endswith('.fcl'):
            return filename.rsplit('.', 1)[0]
        return filename

    def should_convert(self, filename: str) -> bool:
        basename = self._normalize_filename(filename)
        return basename in self.converters

    def should_generate(self, filename: str) -> bool:
        basename = self._normalize_filename(filename)
        return basename in self.generators

class Config:

    def __init__(self, data: Dict[str, Any]):
        try:
            self.app = AppConfig(data.get('app', {}))
            self.app_fuzz = AppFuzzConfig(data.get('app_fuzz', {}))
            self.source_files = SourceFilesConfig(data['source_files'])
            self.artdaq_db = ArtdaqDBConfig(data['artdaq_db'])
            self.ucon_db = UconDBConfig(data['ucon_db'])
            self.reporting = ReportingConfig(data.get('reporting', {}))
            self.carbon = CarbonConfig(data.get('carbon', {}))
            self.fhiclize_generate = FhiclizeGenerateConfig(data.get('fhiclize_generate'))
        except KeyError as e:
            raise ConfigurationError(f"Top-level configuration key missing: '{e.args[0]}'") from e

    @staticmethod
    def from_file(path: str) -> 'Config':
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                raise ConfigurationError(f"Configuration file '{path}' is invalid or empty.")
            data = ConfigExpander.expand_config(data)
            return Config(data)
        except FileNotFoundError as e:
            raise ConfigurationError(f"Configuration file not found at '{path}'.") from e
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Error parsing configuration file '{path}': {e}") from e