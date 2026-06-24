"""
api/meta_graph.py
Meta Graph API — 인스타그램 릴스 데이터 수집 모듈

변경사항:
- get_user_reels() fields에 media_url 추가 (영상 다운로드용)
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://graph.instagram.com/v19.0"
ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")


# ── 사용자 정보 ──────────────────────────────

def get_user_profile(access_token: str = ACCESS_TOKEN) -> dict:
    """
    로그인한 사용자의 인스타그램 비즈니스 계정 정보를 가져옵니다.
    """
    url = f"{BASE_URL}/me"
    params = {
        "fields": "id,username,biography,followers_count,media_count",
        "access_token": access_token,
    }
    res = requests.get(url, params=params)
    res.raise_for_status()
    return res.json()


# ── 릴스 목록 수집 ───────────────────────────

def get_user_reels(
    user_id: str,
    access_token: str = ACCESS_TOKEN,
    limit: int = 50,
) -> list[dict]:
    """
    특정 사용자의 릴스 목록을 가져옵니다. (페이지네이션 포함)
    media_url 포함 — 영상 다운로드 및 프레임 분석에 사용됩니다.

    Returns:
        릴스 dict 리스트
    """
    url = f"{BASE_URL}/{user_id}/media"
    params = {
        "fields": "id,media_type,permalink,timestamp,caption,media_url",  # media_url 추가
        "access_token": access_token,
        "limit": limit,
    }

    all_reels = []
    while url:
        res = requests.get(url, params=params)
        res.raise_for_status()
        data = res.json()

        reels = [item for item in data.get("data", []) if item.get("media_type") == "REEL"]
        all_reels.extend(reels)

        url = data.get("paging", {}).get("next")
        params = {}

    return all_reels


# ── 개별 릴스 성과 지표 수집 ─────────────────

def get_reel_insights(
    media_id: str,
    access_token: str = ACCESS_TOKEN,
) -> dict:
    """
    릴스 1개의 성과 지표를 가져옵니다.
    (조회수, 좋아요, 저장, 공유, 도달)
    """
    url = f"{BASE_URL}/{media_id}/insights"
    params = {
        "metric": "plays,likes,saved,shares,reach,comments",
        "access_token": access_token,
    }
    res = requests.get(url, params=params)
    res.raise_for_status()
    data = res.json()

    insights = {}
    for item in data.get("data", []):
        insights[item["name"]] = item.get("values", [{}])[0].get("value", 0)

    return insights


# ── 통합 수집 함수 ────────────────────────────

def collect_reels_with_insights(
    user_id: str,
    access_token: str = ACCESS_TOKEN,
    limit: int = 30,
) -> list[dict]:
    """
    릴스 목록 + 성과 지표 + media_url을 합쳐서 반환합니다.

    Returns:
        [
            {
                "id": "...",
                "permalink": "...",
                "caption": "...",
                "timestamp": "...",
                "media_url": "...",   ← 영상 다운로드 URL
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


# ── 빠른 테스트 ───────────────────────────────
if __name__ == "__main__":
    profile = get_user_profile()
    print("프로필:", profile)

    user_id = profile.get("id")
    if user_id:
        reels = collect_reels_with_insights(user_id, limit=5)
        for r in reels:
            print(r["id"], r.get("media_url", "URL없음"), r.get("insights"))
