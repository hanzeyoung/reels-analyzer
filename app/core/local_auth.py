"""Supabase가 없을 때 쓰는 로컬 이메일/비밀번호 계정 백엔드 (표준 라이브러리만 사용)."""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")
_MAX_EMAIL = 254
_MIN_PW = 8
_MAX_PW = 128
_MAX_FAILS = 5
_LOCK_SECONDS = 300
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
_BAD_LOGIN = "이메일 또는 비밀번호가 올바르지 않아요."
_DUMMY_SALT = b"\x00" * 16


class AuthError(Exception):
    """str(e)는 사용자에게 그대로 보여줄 한국어 메시지."""


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)


def _normalize_email(email: str) -> str:
    value = (email or "").strip().lower()
    if len(value) > _MAX_EMAIL or not _EMAIL_RE.match(value):
        raise AuthError("이메일 형식을 확인해 주세요.")
    return value


def _check_password(email: str, password: str) -> None:
    if not isinstance(password, str) or len(password) < _MIN_PW:
        raise AuthError(f"비밀번호는 {_MIN_PW}자 이상이어야 해요.")
    if len(password) > _MAX_PW:
        raise AuthError(f"비밀번호는 {_MAX_PW}자 이하로 입력해 주세요.")
    if password.lower() == email.split("@", 1)[0]:
        raise AuthError("비밀번호는 이메일 아이디와 달라야 해요.")


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def _save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{secrets.token_hex(4)}.tmp")
    # 만들 때부터 0600으로 열어, 쓰는 동안에도 다른 사용자가 읽지 못하게 한다.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False))
    tmp.replace(path)


def _session(email: str, record: dict[str, Any]) -> dict[str, str]:
    return {"user_id": record["user_id"], "email": email, "provider": "local"}


def register(path, email: str, password: str, now: float | None = None) -> dict:
    path = Path(path)
    email = _normalize_email(email)
    _check_password(email, password)
    ts = time.time() if now is None else now
    salt = secrets.token_bytes(16)
    digest = _hash(password, salt)  # 락 밖에서 계산
    with _LOCK:
        data = _load(path)
        if email in data:
            raise AuthError("이미 가입된 이메일입니다.")
        record = {
            "user_id": secrets.token_hex(16),
            "salt": salt.hex(),
            "hash": digest.hex(),
            "created_at": ts,
            "failed": 0,
            "locked_until": 0.0,
        }
        data[email] = record
        _save(path, data)
    return _session(email, record)


def authenticate(path, email: str, password: str, now: float | None = None) -> dict:
    path = Path(path)
    ts = time.time() if now is None else now
    try:
        key = _normalize_email(email)
    except AuthError:
        _hash(str(password), _DUMMY_SALT)
        raise AuthError(_BAD_LOGIN) from None
    password = password if isinstance(password, str) else ""

    with _LOCK:
        record = _load(path).get(key)
    if record is None:
        _hash(password, _DUMMY_SALT)  # 응답 시간 맞추기
        raise AuthError(_BAD_LOGIN)

    locked_until = float(record.get("locked_until", 0.0) or 0.0)
    if locked_until > ts:
        minutes = max(1, math.ceil((locked_until - ts) / 60))
        raise AuthError(f"로그인 시도가 너무 많아요. {minutes}분 뒤에 다시 시도해 주세요.")

    try:
        salt = bytes.fromhex(record.get("salt", ""))
        expected = bytes.fromhex(record.get("hash", ""))
    except ValueError:
        salt, expected = _DUMMY_SALT, b""
    ok = hmac.compare_digest(_hash(password, salt), expected)

    with _LOCK:
        data = _load(path)
        current = data.get(key)
        if current is None:
            raise AuthError(_BAD_LOGIN)
        if ok:
            current["failed"] = 0
            current["locked_until"] = 0.0
        else:
            failed = int(current.get("failed", 0) or 0) + 1
            if failed >= _MAX_FAILS:
                current["locked_until"] = ts + _LOCK_SECONDS
                failed = 0
            current["failed"] = failed
        _save(path, data)
    if not ok:
        raise AuthError(_BAD_LOGIN)
    return _session(key, current)


def delete_account(path, user_id: str) -> bool:
    path = Path(path)
    with _LOCK:
        data = _load(path)
        keys = [k for k, v in data.items() if v.get("user_id") == user_id]
        if not keys:
            return False
        for k in keys:
            del data[k]
        _save(path, data)
    return True


def account_count(path) -> int:
    with _LOCK:
        return len(_load(Path(path)))
