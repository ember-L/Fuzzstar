"""Zero-dependency `.env` loader for local development.

:meth:`app.core.config.Settings.from_env` calls :func:`load_env` when it reads
the process environment, so every entry point (API, scripts, worker, mail
worker, Alembic) shares the same configuration. Values
already present in the process environment always win, so containers, CI and
one-off `VAR=value command` overrides stay authoritative.
"""

import os
from pathlib import Path
from typing import Dict, Optional

ENV_PATH = Path(__file__).resolve().parents[2] / '.env'


def parse_env(text: str) -> Dict[str, str]:
    """Parse `KEY=VALUE` lines, tolerating comments, blank lines and quotes."""

    values = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[len('export '):].lstrip()
        key, separator, value = line.partition('=')
        key = key.strip()
        if not separator or not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        values[key] = value
    return values


def load_env(path: Optional[Path] = None) -> Dict[str, str]:
    """Load `.env` into `os.environ` without overriding existing variables."""

    target = Path(path) if path is not None else ENV_PATH
    try:
        text = target.read_text(encoding='utf-8')
    except FileNotFoundError:
        return {}
    loaded = parse_env(text)
    for key, value in loaded.items():
        os.environ.setdefault(key, value)
    return loaded
