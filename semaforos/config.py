import json
import os
from pathlib import Path


def load_config(path=None):
    value = json.loads(Path(path or os.getenv('SC_MODEL_CONFIG', 'config/modelos.json')).read_text())
    if value.get('schema_version') != 1:
        raise ValueError('unsupported_config_version')
    for stage in ('audio','detect','lights','text','video'):
        if not isinstance(value.get(stage), dict):raise ValueError('missing_stage_config')
    if not 1 <= value['max_attempts'] <= 5:raise ValueError('invalid_max_attempts')
    if not 30 <= value['timeout_seconds'] <= 14400:raise ValueError('invalid_timeout')
    return value


def storage_root():
    root = Path(os.getenv('SC_STORAGE', '/data/core'))
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()
