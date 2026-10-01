"""Server-side, single-use OAuth state.

Streamlit keeps ``st.session_state`` per browser connection, and the OAuth redirect comes back
as a brand-new page load, so the state cannot live in the session. Only a SHA-256 digest of each
state is stored, bound to the owner that requested it, and removed on first use.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from pathlib import Path

DEFAULT_TTL_SECONDS = 15 * 60
MAX_PENDING = 200
_LOCK = threading.Lock()


def _digest(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(path: Path, rows: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    try:
        temp.chmod(0o600)
    except OSError:
        pass  # permission bits are not meaningful on every platform
    temp.replace(path)


def _alive(rows: dict, now: float) -> dict:
    return {key: row for key, row in rows.items() if isinstance(row, dict) and float(row.get("exp", 0)) > now}


def issue_state(path: str | Path, owner: str, ttl: int = DEFAULT_TTL_SECONDS, now: float | None = None) -> str:
    """Create a random state valid for ``ttl`` seconds and bound to ``owner``."""
    current = time.time() if now is None else now
    state = secrets.token_urlsafe(32)
    target = Path(path)
    with _LOCK:
        rows = _alive(_read(target), current)
        rows[_digest(state)] = {"owner": str(owner), "exp": current + ttl}
        if len(rows) > MAX_PENDING:
            newest = sorted(rows.items(), key=lambda item: item[1]["exp"], reverse=True)[:MAX_PENDING]
            rows = dict(newest)
        _write(target, rows)
    return state


def consume_state(path: str | Path, state: str, owner: str, now: float | None = None) -> bool:
    """Return True once for a valid, unexpired state that belongs to ``owner``; it is then spent."""
    if not isinstance(state, str) or not state:
        return False
    current = time.time() if now is None else now
    key = _digest(state)
    target = Path(path)
    with _LOCK:
        rows = _read(target)
        row = rows.get(key)
        if not isinstance(row, dict):
            return False
        if float(row.get("exp", 0)) <= current:
            _write(target, _alive(rows, current))
            return False
        if row.get("owner") != str(owner):
            # Someone else's pending state: refuse without spending it.
            return False
        rows.pop(key)
        _write(target, _alive(rows, current))
    return True
