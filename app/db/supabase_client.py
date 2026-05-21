"""
db/supabase_client.py
Supabase 연결 및 CRUD 함수 모음
"""

import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Client | None = None


def get_client() -> Client:
    """Supabase 클라이언트 싱글톤 반환"""
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_ANON_KEY")
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
