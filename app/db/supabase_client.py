"""
db/supabase_client.py
Supabase 연결 및 CRUD 함수 모음
"""

from contextvars import ContextVar

try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = object
from dotenv import load_dotenv

from app.core.config import get_env
from app.core.performance_insights import normalize_insights, performance_score

load_dotenv()

_client: Client | None = None
_auth_session: ContextVar[tuple[str, str] | None] = ContextVar("supabase_auth_session", default=None)
_service_role_enabled: ContextVar[bool] = ContextVar("supabase_service_role_enabled", default=False)


def configure_auth_session(access_token: str = "", refresh_token: str = "") -> None:
    """Bind a Supabase user session to the current Streamlit execution context."""
    _auth_session.set((access_token, refresh_token) if access_token and refresh_token else None)


def configure_service_role(enabled: bool = False) -> None:
    """Enable server-only service credentials for unattended jobs in this context."""
    _service_role_enabled.set(bool(enabled))


def get_client() -> Client:
    """Supabase 클라이언트 싱글톤 반환"""
    if create_client is None:
        raise RuntimeError("Supabase 연동을 사용하려면 supabase 패키지를 설치해주세요.")
    if _service_role_enabled.get():
        service_key = get_env("SUPABASE_SERVICE_ROLE_KEY")
        if not service_key:
            raise ValueError("예약 저장에는 SUPABASE_SERVICE_ROLE_KEY가 필요합니다.")
        return create_client(get_env("SUPABASE_URL"), service_key)
    auth_session = _auth_session.get()
    if auth_session:
        client = create_client(get_env("SUPABASE_URL"), get_env("SUPABASE_ANON_KEY"))
        client.auth.set_session(*auth_session)
        return client

    global _client
    if _client is None:
        url = get_env("SUPABASE_URL")
        key = get_env("SUPABASE_ANON_KEY")
        if not url or not key:
            raise ValueError(".env에 SUPABASE_URL과 SUPABASE_ANON_KEY를 설정해주세요.")
        _client = create_client(url, key)
    return _client


# ── 릴스 저장 ────────────────────────────────

def upsert_reel(reel_data: dict) -> dict:
    """
    릴스 데이터를 DB에 저장합니다. (중복이면 업데이트)

    Args:
        reel_data: reels 테이블 컬럼과 일치하는 dict
    """
    client = get_client()
    res = client.table("reels").upsert(reel_data, on_conflict="instagram_media_id").execute()
    return res.data


def upsert_user(user_data: dict) -> dict:
    client = get_client()
    res = client.table("users").upsert(user_data, on_conflict="instagram_user_id").execute()
    return res.data[0] if res.data else {}


def upsert_store(store_data: dict) -> dict:
    client = get_client()
    res = client.table("stores").upsert(store_data, on_conflict="store_key").execute()
    return res.data[0] if res.data else {}


def upsert_score(score_data: dict) -> dict:
    """스코어 결과를 DB에 저장합니다."""
    client = get_client()
    res = client.table("reel_scores").upsert(score_data, on_conflict="reel_id").execute()
    return res.data


def upsert_analysis(analysis_data: dict) -> dict:
    """AI 분석 결과를 DB에 저장합니다."""
    client = get_client()
    res = client.table("reel_analysis").upsert(analysis_data, on_conflict="reel_id").execute()
    return res.data


def insert_performance_snapshot(snapshot_data: dict) -> dict:
    """Meta 실측 성과의 시계열 스냅샷을 저장합니다."""
    client = get_client()
    res = client.table("reel_performance_snapshots").insert(snapshot_data).execute()
    return res.data


def insert_market_snapshot(snapshot_data: dict) -> dict:
    """지역·업종별 공개 릴스 시장 스냅샷을 저장합니다."""
    client = get_client()
    res = client.table("market_snapshots").insert(snapshot_data).execute()
    return res.data


def upsert_creator_pattern(pattern_data: dict) -> dict:
    """사용자별 누적 성공 패턴을 저장합니다."""
    client = get_client()
    res = client.table("creator_patterns").upsert(pattern_data, on_conflict="user_id").execute()
    return res.data


def sync_meta_account(
    profile: dict,
    reels: list[dict],
    business_type: str,
    store_profile: dict,
    auth_user_id: str = "",
) -> dict:
    """Persist one Meta sync transaction set; callers can fall back to local storage on failure."""
    user = upsert_user({
        "instagram_user_id": str(profile["id"]),
        "username": profile.get("username") or str(profile["id"]),
        "business_type": business_type,
        **({"auth_user_id": auth_user_id} if auth_user_id else {}),
    })
    store = upsert_store({
        "user_id": user.get("id"),
        "store_key": store_profile.get("store_id") or "default",
        "name": store_profile.get("name") or profile.get("username") or "Instagram store",
        "business_type": business_type,
        "place": store_profile.get("place"),
        "primary_product": store_profile.get("menu"),
        "profile_data": store_profile,
    })
    synced = 0
    for item in reels:
        insights = normalize_insights(item.get("insights"))
        reel_rows = upsert_reel({
            "instagram_media_id": str(item["id"]),
            "user_id": user.get("id"),
            "store_id": store.get("id"),
            "business_type": business_type,
            "permalink": item.get("permalink"),
            "thumbnail_url": item.get("thumbnail_url"),
            "caption": item.get("caption"),
            "view_count": int(insights["views"]),
            "like_count": int(insights["likes"] or item.get("like_count") or 0),
            "comment_count": int(insights["comments"] or item.get("comments_count") or 0),
            "save_count": int(insights["saved"]),
            "share_count": int(insights["shares"]),
            "reach": int(insights["reach"]),
            "published_at": item.get("timestamp"),
        })
        reel = reel_rows[0] if isinstance(reel_rows, list) and reel_rows else {}
        if reel.get("id"):
            insert_performance_snapshot({
                "reel_id": reel["id"],
                "views": int(insights["views"]),
                "reach": int(insights["reach"]),
                "likes": int(insights["likes"]),
                "comments": int(insights["comments"]),
                "saved": int(insights["saved"]),
                "shares": int(insights["shares"]),
                "avg_watch_time_ms": int(insights["avg_watch_time_ms"]),
                "total_watch_time_ms": int(insights["watch_time_ms"]),
                "measured_score": performance_score(insights),
            })
            synced += 1
    return {"user": user, "store": store, "synced_reels": synced}


def save_analysis_for_instagram_media(instagram_media_id: str, analysis: dict) -> dict:
    client = get_client()
    reel_response = (
        client.table("reels")
        .select("id")
        .eq("instagram_media_id", str(instagram_media_id))
        .limit(1)
        .execute()
    )
    if not reel_response.data:
        raise ValueError("Supabase에서 해당 Instagram 릴스를 찾지 못했습니다.")
    return upsert_analysis({
        "reel_id": reel_response.data[0]["id"],
        "camera_angles": analysis.get("camera_angles", []),
        "cut_speed": analysis.get("cut_speed"),
        "hook_text": analysis.get("hook_text"),
        "subtitle_position": analysis.get("subtitle_position"),
        "color_tone": analysis.get("color_tone"),
        "bgm_mood": analysis.get("bgm_mood"),
        "caption_hooks": analysis.get("caption_hooks", []),
        "analysis_summary": analysis.get("analysis_summary"),
        "raw_gemini_response": analysis,
        "category_scores": analysis.get("category_scores", {}),
        "overall_score": analysis.get("overall_score"),
        "timeline_diagnostics": analysis.get("timeline_diagnostics", []),
        "timeline_signals": analysis.get("timeline_signals", []),
        "signal_summary": analysis.get("signal_summary", {}),
        "priority_actions": analysis.get("priority_actions", []),
        "analysis_basis": analysis.get("analysis_basis"),
        "prediction_confidence": analysis.get("prediction_confidence"),
    })


# ── 릴스 조회 ────────────────────────────────

def get_top_reels(
    business_type: str,
    limit: int = 10,
) -> list[dict]:
    """
    업종별 상위 릴스를 점수 순으로 가져옵니다.
    (reels + reel_scores JOIN)
    """
    client = get_client()
    res = (
        client.table("reels")
        .select("*, reel_scores(total_score, tier, score_tier)")
        .eq("business_type", business_type)
        .order("reel_scores.total_score", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data


def get_latest_trend_report(business_type: str) -> dict | None:
    """가장 최신 트렌드 리포트를 가져옵니다."""
    client = get_client()
    res = (
        client.table("trend_reports")
        .select("*")
        .eq("business_type", business_type)
        .order("week_start", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def get_reel_with_analysis(reel_id: str) -> dict | None:
    """릴스 + AI 분석 결과를 함께 가져옵니다."""
    client = get_client()
    res = (
        client.table("reels")
        .select("*, reel_analysis(*), reel_scores(*)")
        .eq("id", reel_id)
        .single()
        .execute()
    )
    return res.data


# ── 빠른 연결 테스트 ─────────────────────────
if __name__ == "__main__":
    client = get_client()
    print("Supabase 연결 성공!")
    res = client.table("reels").select("id").limit(1).execute()
    print("reels 테이블 확인:", res.data)
