from __future__ import annotations

import json
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def _cipher(encryption_key: str) -> Fernet:
    if not encryption_key:
        raise ValueError("META_TOKEN_ENCRYPTION_KEY is required")
    try:
        return Fernet(encryption_key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise ValueError("META_TOKEN_ENCRYPTION_KEY must be a valid Fernet key") from exc


def save_encrypted_token(token: str, encryption_key: str, path: str | Path, metadata: dict | None = None) -> Path:
    if not token:
        raise ValueError("Token is empty")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"token": token, "metadata": metadata or {}}, ensure_ascii=False).encode("utf-8")
    target.write_bytes(_cipher(encryption_key).encrypt(payload))
    return target


def load_encrypted_token(encryption_key: str, path: str | Path) -> dict | None:
    target = Path(path)
    if not target.exists() or not encryption_key:
        return None
    try:
        payload = _cipher(encryption_key).decrypt(target.read_bytes())
        result = json.loads(payload.decode("utf-8"))
    except (OSError, InvalidToken, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return result if isinstance(result, dict) and result.get("token") else None


def delete_encrypted_token(path: str | Path) -> bool:
    target = Path(path)
    if not target.exists():
        return False
    target.unlink()
    return True
