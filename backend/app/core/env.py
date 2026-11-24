"""Zero-dependency `.env` loader for local development.

Two files are read, in this order:

1. ``team.env`` — committed to the repository, holds the team's shared
   defaults. Teammates only edit ``SERVER_HOST`` there to point at whoever
   runs MySQL, and ``DATABASE_URL`` is composed from it automatically.
2. ``.env`` — git-ignored, personal overrides. Always wins over ``team.env``.

:meth:`app.core.config.Settings.from_env` calls :func:`load_env` when it reads
the process environment, so every entry point (API, scripts, worker, mail
worker, Alembic) shares the same configuration. Values
already present in the process environment always win, so containers, CI and
one-off `VAR=value command` overrides stay authoritative.
"""

import os
from pathlib import Path
from typing import Dict, Mapping, Optional
from urllib.parse import quote_plus

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = BACKEND_ROOT / '.env'
TEAM_ENV_PATH = BACKEND_ROOT / 'team.env'

DEFAULT_DB_PORT = '3306'
DEFAULT_DB_NAME = 'rongxing'
DEFAULT_DB_USER = 'rongxing'


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


def _read(path: Path) -> Dict[str, str]:
    try:
        return parse_env(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}


def build_database_url(env: Mapping[str, str]) -> Optional[str]:
    """Compose ``DATABASE_URL`` from ``SERVER_HOST`` and the ``DB_*`` defaults.

    Returns ``None`` when ``SERVER_HOST`` is missing, so callers can keep
    requiring an explicit ``DATABASE_URL``. This is what lets teammates point
    the whole project at a new host by editing a single line in ``team.env``.
    """

    host = (env.get('SERVER_HOST') or '').strip()
    if not host:
        return None
    user = (env.get('DB_USER') or DEFAULT_DB_USER).strip()
    password = env.get('DB_PASSWORD') or ''
    port = (env.get('DB_PORT') or DEFAULT_DB_PORT).strip()
    name = (env.get('DB_NAME') or DEFAULT_DB_NAME).strip()
    return (f'mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}'
            f'@{host}:{port}/{name}?charset=utf8mb4')


def load_env(path: Optional[Path] = None) -> Dict[str, str]:
    """Load configuration into `os.environ` without overriding existing values.

    With no argument, ``team.env`` is loaded first and ``.env`` second, so the
    personal file takes precedence; ``DATABASE_URL`` is derived from
    ``SERVER_HOST`` when nothing else defines it. Passing an explicit path
    keeps the single-file behaviour used by the tests.
    """

    if path is not None:
        loaded = _read(Path(path))
        for key, value in loaded.items():
            os.environ.setdefault(key, value)
        return loaded

    loaded: Dict[str, str] = {}
    for target in (TEAM_ENV_PATH, ENV_PATH):
        values = _read(target)
        loaded.update(values)
        for key, value in values.items():
            os.environ.setdefault(key, value)

    if not os.environ.get('DATABASE_URL'):
        derived = build_database_url(os.environ)
        if derived:
            os.environ['DATABASE_URL'] = derived
            loaded['DATABASE_URL'] = derived
    return loaded
