"""
api/meta_graph.py
Meta Graph API — 인스타그램 릴스 데이터 수집 모듈
"""

import requests
import secrets
from urllib.parse import urlencode
from dotenv import load_dotenv

from app.core.config import get_env
from app.core.performance_insights import normalize_insights

load_dotenv()

GRAPH_VERSION = get_env("META_GRAPH_API_VERSION", "v24.0")
BASE_URL = f"https://graph.instagram.com/{GRAPH_VERSION}"
ACCESS_TOKEN = get_env("META_ACCESS_TOKEN")
INSIGHT_METRICS = [
    "views",
    "plays",
    "reach",
    "saved",
    "shares",
    "comments",
    "likes",
    "total_interactions",
    "ig_reels_avg_watch_time",
    "ig_reels_video_view_total_time",
]
OAUTH_AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
OAUTH_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
DEFAULT_SCOPES = "instagram_business_basic,instagram_business_manage_insights"


def _require_token(access_token: str | None = None) -> str:
    access_token = access_token or get_env("META_ACCESS_TOKEN")
    if not access_token:
        raise ValueError("META_ACCESS_TOKEN이 설정되지 않았습니다.")
    return access_token


# ── 사용자 정보 ──────────────────────────────

def build_oauth_url(state: str | None = None, redirect_uri: str | None = None) -> tuple[str, str]:
    """Build an Instagram Business Login URL when Meta app settings are present."""
    app_id = get_env("META_APP_ID")
    redirect_uri = redirect_uri or get_env("META_REDIRECT_URI")
    if not app_id or not redirect_uri:
        raise ValueError("META_APP_ID와 META_REDIRECT_URI를 설정해주세요.")
    state = state or secrets.token_urlsafe(24)
    params = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": get_env("META_OAUTH_SCOPES", DEFAULT_SCOPES),
        "state": state,
    }
    return f"{OAUTH_AUTHORIZE_URL}?{urlencode(params)}", state


def exchange_authorization_code(code: str, redirect_uri: str | None = None) -> dict:
    """Exchange an OAuth callback code and upgrade it to a long-lived token when possible."""
    app_id = get_env("META_APP_ID")
    app_secret = get_env("META_APP_SECRET")
    redirect_uri = redirect_uri or get_env("META_REDIRECT_URI")
    if not all([app_id, app_secret, redirect_uri, code]):
        raise ValueError("OAuth 코드 교환에 필요한 Meta 앱 설정이 부족합니다.")
    response = requests.post(
        OAUTH_TOKEN_URL,
        data={
            "client_id": app_id,
            "client_secret": app_secret,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=30,
    )
    response.raise_for_status()
    short_lived = response.json()
    token = short_lived.get("access_token")
    if not token:
        return short_lived
    long_response = requests.get(
        "https://graph.instagram.com/access_token",
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": app_secret,
            "access_token": token,
        },
        timeout=30,
    )
    if long_response.ok:
        return {**short_lived, **long_response.json(), "token_type": "long_lived"}
    return {**short_lived, "token_type": "short_lived"}


def refresh_access_token(access_token: str) -> dict:
    response = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": access_token},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_user_profile(access_token: str | None = None) -> dict:
    """
    로그인한 사용자의 인스타그램 비즈니스 계정 정보를 가져옵니다.
    """
    access_token = _require_token(access_token)
    url = f"{BASE_URL}/me"
    params = {
        "fields": "id,username,biography,followers_count,media_count",
        "access_token": access_token,
    }
    res = requests.get(url, params=params, timeout=30)
    res.raise_for_status()
    return res.json()


# ── 릴스 목록 수집 ───────────────────────────

def get_user_reels(
    user_id: str,
    access_token: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """
    특정 사용자의 릴스 목록을 가져옵니다. (페이지네이션 포함)

    Returns:
        릴스 dict 리스트
    """
    access_token = _require_token(access_token)
    url = f"{BASE_URL}/{user_id}/media"
    params = {
        "fields": "id,media_type,media_product_type,permalink,timestamp,caption,thumbnail_url,media_url,like_count,comments_count",
        "access_token": access_token,
        "limit": limit,
    }

    all_reels = []
    while url:
        res = requests.get(url, params=params, timeout=30)
        res.raise_for_status()
        data = res.json()

        # REEL 타입만 필터링
        reels = [
            item for item in data.get("data", [])
            if item.get("media_type") == "REEL" or item.get("media_product_type") == "REELS"
        ]
        all_reels.extend(reels)
        if len(all_reels) >= limit:
            return all_reels[:limit]

        # 다음 페이지 확인
        url = data.get("paging", {}).get("next")
        params = {}  # next URL에는 이미 파라미터가 포함되어 있음

    return all_reels


# ── 개별 릴스 성과 지표 수집 ─────────────────

def get_reel_insights(
    media_id: str,
    access_token: str | None = None,
) -> dict:
    """
    릴스 1개의 성과 지표를 가져옵니다.
    (조회수, 좋아요, 저장, 공유, 도달)
    """
    access_token = _require_token(access_token)
    url = f"{BASE_URL}/{media_id}/insights"
    insights = {}

    # API versions and account types expose different metric sets. Requesting each
    # metric separately prevents one unsupported name from breaking the full sync.
    for metric in INSIGHT_METRICS:
        res = requests.get(
            url,
            params={"metric": metric, "access_token": access_token},
            timeout=30,
        )
        if res.status_code >= 400:
            continue
        for item in res.json().get("data", []):
            value = item.get("values", [{}])[0].get("value", item.get("total_value", {}).get("value", 0))
            insights[item["name"]] = value

    return normalize_insights(insights)


# ── 한번에 수집하는 통합 함수 ────────────────

def collect_reels_with_insights(
    user_id: str,
    access_token: str | None = None,
    limit: int = 30,
) -> list[dict]:
    """
    릴스 목록 + 각 릴스의 성과 지표를 합쳐서 반환합니다.

    Returns:
        [
            {
                "id": "...",
                "permalink": "...",
                "caption": "...",
                "timestamp": "...",
                "insights": { "plays": 0, "likes": 0, ... }
            },
            ...
        ]
    """
    reels = get_user_reels(user_id, access_token, limit)
    result = []

    for reel in reels:
        try:
            insights = get_reel_insights(reel["id"], access_token)
            reel["insights"] = insights
        except Exception as e:
            print(f"[경고] {reel['id']} insights 수집 실패: {e}")
            reel["insights"] = {}
        result.append(reel)

    return result


def collect_my_reels(access_token: str | None = None, limit: int = 30) -> dict:
    """Resolve the connected profile and return a normalized account payload."""
    access_token = _require_token(access_token)
    profile = get_user_profile(access_token)
    reels = collect_reels_with_insights(profile["id"], access_token=access_token, limit=limit)
    return {"profile": profile, "reels": reels, "graph_version": GRAPH_VERSION}


# ── 빠른 테스트 ───────────────────────────────
if __name__ == "__main__":
    # 실제 실행 전에 .env에 META_ACCESS_TOKEN 설정 필요
    profile = get_user_profile()
    print("프로필:", profile)

    user_id = profile.get("id")
    if user_id:
        reels = collect_reels_with_insights(user_id, limit=5)
        for r in reels:
            print(r["id"], r.get("insights"))
