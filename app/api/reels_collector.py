# reels_collector.py

import os
import math
import pandas as pd
from dotenv import load_dotenv
from apify_client import ApifyClient

# 1. 환경 변수 로드
load_dotenv()

# 2. Apify 설정
APIFY_TOKEN = os.getenv("APIFY_TOKEN")
ACTOR_ID = "patient_discovery/instagram-search-reels"

if not APIFY_TOKEN:
    raise ValueError("APIFY_TOKEN이 없습니다. .env 파일을 확인하세요.")


def get_reels_data(keyword, max_items=30):
    """
    Apify Actor를 사용해 일반 키워드 검색 기반 릴스 데이터를 가져오는 함수
    """
    client = ApifyClient(APIFY_TOKEN)

    # 주의: 이 input key는 Actor의 Input 탭에 따라 다를 수 있음
    run_input = {
        "searchQuery": keyword,
        "maxItems": max_items
    }

    run = client.actor(ACTOR_ID).call(run_input=run_input)

    items = list(
        client
        .dataset(run["defaultDatasetId"])
        .iterate_items()
    )

    return items


def safe_get_number(item, key):
    """
    None 값 방지용 숫자 추출 함수
    """
    value = item.get(key, 0)

    if value is None:
        return 0

    return value


def calculate_buza_score(item):
    """
    릴스 성과 점수 계산 함수

    원본 수치를 그대로 더하면 조회수가 너무 커서 점수가 왜곡됨.
    따라서 log1p를 사용해 큰 숫자의 영향력을 줄임.

    Score = 조회수 0.35 + 좋아요 0.25 + 댓글 0.15 + 공유 0.25
    """
    play = safe_get_number(item, "ig_play_count")
    like = safe_get_number(item, "like_count")
    comment = safe_get_number(item, "comment_count")
    share = safe_get_number(item, "share_count")

    score = (
        math.log1p(play) * 0.35 +
        math.log1p(like) * 0.25 +
        math.log1p(comment) * 0.15 +
        math.log1p(share) * 0.25
    )

    return round(score, 4)


def make_reel_url(item):
    """
    code 값을 이용해 인스타그램 릴스 URL 생성
    """
    code = item.get("code")

    if not code:
        return ""

    return f"https://www.instagram.com/reel/{code}/"


def process_reels(raw_data):
    """
    API에서 받은 원본 데이터를 프로젝트에서 쓰기 좋은 형태로 가공
    """
    processed_reels = []

    for reel in raw_data:
        # 영상이 아니거나 video_url이 없으면 제외
        if not reel.get("is_video"):
            continue

        if not reel.get("video_url"):
            continue

        caption = reel.get("caption", {})
        if isinstance(caption, dict):
            caption_text = caption.get("text", "")
        else:
            caption_text = caption or ""

        user = reel.get("user", {})
        if not isinstance(user, dict):
            user = {}

        clips_metadata = reel.get("clips_metadata", {})
        if not isinstance(clips_metadata, dict):
            clips_metadata = {}

        original_sound_info = clips_metadata.get("original_sound_info", {})
        if not isinstance(original_sound_info, dict):
            original_sound_info = {}

        score = calculate_buza_score(reel)

        processed_reels.append({
            "rank_score": score,
            "id": reel.get("id"),
            "code": reel.get("code"),
            "url": make_reel_url(reel),
            "username": user.get("username"),
            "full_name": user.get("full_name"),
            "is_verified": user.get("is_verified"),
            "caption": caption_text,
            "ig_play_count": safe_get_number(reel, "ig_play_count"),
            "like_count": safe_get_number(reel, "like_count"),
            "comment_count": safe_get_number(reel, "comment_count"),
            "share_count": safe_get_number(reel, "share_count"),
            "video_url": reel.get("video_url"),
            "video_duration": reel.get("video_duration"),
            "thumbnail_url": reel.get("thumbnail_url"),
            "taken_at": reel.get("taken_at"),
            "taken_at_date": reel.get("taken_at_date"),
            "audio_title": original_sound_info.get("original_audio_title"),
            "has_audio": reel.get("has_audio"),
        })

    return processed_reels


def get_top_reels(keyword, max_items=30, top_n=10):
    """
    키워드 검색 → 릴스 수집 → 스코어링 → Top N 반환
    """
    raw_data = get_reels_data(keyword, max_items=max_items)
    processed_reels = process_reels(raw_data)

    top_reels = sorted(
        processed_reels,
        key=lambda x: x["rank_score"],
        reverse=True
    )[:top_n]

    return top_reels


# 3. 메인 실행부
if __name__ == "__main__":
    test_keyword = "성수동 카페 인테리어"

    top_reels = get_top_reels(
        keyword=test_keyword,
        max_items=30,
        top_n=5
    )

    df = pd.DataFrame(top_reels)

    if df.empty:
        print("수집된 릴스가 없습니다. Actor input 형식 또는 검색어를 확인하세요.")
    else:
        print(df[[
            "rank_score",
            "url",
            "username",
            "ig_play_count",
            "like_count",
            "comment_count",
            "share_count",
            "video_url"
        ]])