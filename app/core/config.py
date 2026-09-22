from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


def get_env(name: str, default: str = "") -> str:
    """Return a trimmed environment value without surrounding quotes."""
    value = os.getenv(name, default)
    if value is None:
        return default
    return value.strip().strip('"').strip("'").strip()


def has_env(name: str) -> bool:
    return bool(get_env(name))


def get_env_bool(name: str, default: bool = False) -> bool:
    value = get_env(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def require_env(name: str, purpose: str) -> str:
    value = get_env(name)
    if not value:
        raise RuntimeError(f"{purpose}에 필요한 {name} 값이 없습니다. .env 파일을 확인하세요.")
    return value


def get_gemini_api_key() -> str:
    return get_env("GEMINI_API_KEY") or get_env("GOOGLE_API_KEY")


def get_gemini_model() -> str:
    configured = get_env("GEMINI_MODEL", "gemini-3.8-flash")
    # Gemini 1.5 endpoints were retired. Transparently migrate old local .env
    # values so existing installations can analyze thumbnails again.
    if configured.startswith("gemini-1.5"):
        return "gemini-3.8-flash"
    return configured
