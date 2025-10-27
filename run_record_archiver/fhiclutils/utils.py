import re
from typing import List, Any

def is_numeric(value: str) -> bool:
    if not value or not re.match('^[0-9.]+$', value):
        return False
    return value.count('.') <= 1

def normalize_key(key: str) -> str:
    normalized = re.sub('[\\s\\-()/#.]+', '_', key.strip())
    return normalized

def quote_value(value: str) -> str:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value
    if value.startswith('[') and value.endswith(']'):
        return value
    if is_numeric(value):
        return value
    escaped = value.replace('"', '\\"')
    return f'"{escaped}"'

def format_fhicl_array(items: List[str]) -> str:
    if not items:
        return '[]'
    quoted_items = [f'"{item}"' for item in items]
    return '[' + ', '.join(quoted_items) + ']'

def clean_non_ascii(text: str) -> str:
    return ''.join((c if ord(c) < 128 else '.' for c in text))

def strip_comments(line: str) -> str:
    if '#' in line:
        line = line[:line.index('#')]
    return line.strip()