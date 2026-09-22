from __future__ import annotations

from typing import Any

try:
    from supabase import create_client
except ImportError:
    create_client = None

from app.core.config import get_env, require_env


def _auth_client():
    if create_client is None:
        raise RuntimeError("Supabase 연동을 사용하려면 supabase 패키지를 설치해주세요.")
    return create_client(
        require_env("SUPABASE_URL", "로그인"),
        require_env("SUPABASE_ANON_KEY", "로그인"),
    )


def _session_payload(response: Any) -> dict:
    session = getattr(response, "session", None)
    user = getattr(response, "user", None)
    if not session or not user:
        return {}
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expires_at": getattr(session, "expires_at", None),
        "user_id": str(user.id),
        "email": getattr(user, "email", "") or "",
    }


def sign_in(email: str, password: str) -> dict:
    response = _auth_client().auth.sign_in_with_password({"email": email, "password": password})
    payload = _session_payload(response)
    if not payload:
        raise RuntimeError("로그인 세션을 만들지 못했습니다.")
    return payload


def sign_up(email: str, password: str) -> dict:
    response = _auth_client().auth.sign_up({"email": email, "password": password})
    return _session_payload(response)


def refresh_session(access_token: str, refresh_token: str) -> dict:
    client = _auth_client()
    response = client.auth.set_session(access_token, refresh_token)
    return _session_payload(response)


def auth_is_configured() -> bool:
    return bool(get_env("SUPABASE_URL") and get_env("SUPABASE_ANON_KEY"))


def delete_cloud_account(user_id: str) -> None:
    if create_client is None:
        raise RuntimeError("Supabase 연동을 사용하려면 supabase 패키지를 설치해주세요.")
    service_key = require_env("SUPABASE_SERVICE_ROLE_KEY", "계정 삭제")
    client = create_client(require_env("SUPABASE_URL", "계정 삭제"), service_key)
    client.auth.admin.delete_user(user_id)
