"""
api/meta_graph.py
Meta Graph API — 인스타그램 릴스 데이터 수집 모듈
"""

import os
import requests
from typing import Optional
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

    Returns:
        릴스 dict 리스트
    """
    url = f"{BASE_URL}/{user_id}/media"
    params = {
        "fields": "id,media_type,permalink,timestamp,caption",
        "access_token": access_token,
        "limit": limit,
    }

    all_reels = []
    while url:
        res = requests.get(url, params=params)
        res.raise_for_status()
        data = res.json()

        # REEL 타입만 필터링
        reels = [item for item in data.get("data", []) if item.get("media_type") == "REEL"]
        all_reels.extend(reels)

        # 다음 페이지 확인
        url = data.get("paging", {}).get("next")
        params = {}  # next URL에는 이미 파라미터가 포함되어 있음

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

    # 지표를 dict로 정리
    insights = {}
    for item in data.get("data", []):
        insights[item["name"]] = item.get("values", [{}])[0].get("value", 0)

    return insights


# ── 한번에 수집하는 통합 함수 ────────────────

def collect_reels_with_insights(
    user_id: str,
    access_token: str = ACCESS_TOKEN,
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
