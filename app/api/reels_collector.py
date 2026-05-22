# reels_collector.py

import os
import math
import time
from pathlib import Path

import re
import requests
import pandas as pd
from dotenv import load_dotenv

# 1. 환경 변수 로드
load_dotenv()

# 2. Apify 설정
APIFY_TOKEN = os.getenv("APIFY_TOKEN")
ACTOR_ID = "patient_discovery/instagram-search-reels"

if not APIFY_TOKEN:
    raise ValueError("APIFY_TOKEN이 없습니다. .env 파일을 확인하세요.")


def get_reels_data(keyword: str, max_items: int = 20) -> list[dict]:
    """
    Apify REST API를 직접 호출해서 검색어 기반 릴스 데이터를 가져온다.
    apify-client의 Pydantic 검증 오류를 우회하기 위한 방식.
    """
    run_input = {
        "searchQuery": keyword,
        "maxItems": max_items,
    }

    headers = {
        "Authorization": f"Bearer {APIFY_TOKEN}",
        "Content-Type": "application/json",
    }

    # Actor ID는 URL에서 / 대신 ~ 사용
    actor_id_for_url = ACTOR_ID.replace("/", "~")

    # 1. Actor 실행
    start_url = f"https://api.apify.com/v2/acts/{actor_id_for_url}/runs"

    start_res = requests.post(
        start_url,
        headers=headers,
        json=run_input,
        timeout=60,
    )

    start_res.raise_for_status()

    run_data = start_res.json()["data"]
    run_id = run_data["id"]

    print(f"[Apify] Actor 실행 시작: {run_id}")

    # 2. Actor 실행 완료까지 대기
    while True:
        status_url = f"https://api.apify.com/v2/actor-runs/{run_id}"

        status_res = requests.get(
            status_url,
            headers=headers,
            timeout=30,
        )

        status_res.raise_for_status()

        status_data = status_res.json()["data"]
        status = status_data["status"]

        print(f"[Apify] 현재 상태: {status}")

        if status == "SUCCEEDED":
            dataset_id = status_data["defaultDatasetId"]
            break

        if status in ["FAILED", "ABORTED", "TIMED-OUT"]:
            raise RuntimeError(f"Apify Actor 실행 실패: {status}")

        time.sleep(5)

    # 3. 결과 Dataset 가져오기
    dataset_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items"

    dataset_res = requests.get(
        dataset_url,
        headers=headers,
        params={"clean": "true"},
        timeout=60,
    )

    dataset_res.raise_for_status()

    return dataset_res.json()


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


    # 전체 검색어가 캡션에 있으면 통과

def process_reels(raw_data: list[dict], keyword: str) -> list[dict]:
    processed = []

    for reel in raw_data:
        if reel.get("is_video") is not True:
            continue

        if not reel.get("video_url"):
            continue

        # 검색어와 관련 없는 릴스 제거
        if not is_relevant_reel(reel, keyword):
            continue

        user = reel.get("user", {})
        if not isinstance(user, dict):
            user = {}

        processed.append({
            "rank_score": calculate_score(reel),
            "id": reel.get("id"),
            "code": reel.get("code"),
            "url": make_reel_url(reel),
            "username": user.get("username"),
            "caption": get_caption_text(reel),
            "ig_play_count": safe_number(reel.get("ig_play_count")),
            "like_count": safe_number(reel.get("like_count")),
            "comment_count": safe_number(reel.get("comment_count")),
            "share_count": safe_number(reel.get("share_count")),
            "video_url": reel.get("video_url"),
            "thumbnail_url": reel.get("thumbnail_url"),
            "video_duration": reel.get("video_duration"),
            "audio_title": get_audio_title(reel),
            "has_audio": reel.get("has_audio"),
            "taken_at": reel.get("taken_at"),
            "taken_at_date": reel.get("taken_at_date"),
        })

    return processed

def get_top_reels(keyword: str, max_items: int = 20, top_n: int = 5) -> list[dict]:
    raw_data = get_reels_data(keyword, max_items=max_items)
    processed = process_reels(raw_data, keyword)

    top_reels = sorted(
        processed,
        key=lambda x: x["rank_score"],
        reverse=True
    )[:top_n]

    return top_reels

def safe_filename(text: str) -> str:
    """
    파일명에 쓸 수 없는 문자를 제거한다.
    """
    if not text:
        return "unknown"

    return re.sub(r'[\\/:*?"<>|]', "_", text)


def download_reel_video(video_url: str, code: str, save_dir: str = "videos") -> str:
    """
    video_url을 이용해 릴스 영상을 mp4 파일로 저장한다.

    Args:
        video_url: Apify에서 받은 직접 영상 URL
        code: 릴스 code 값
        save_dir: 저장 폴더

    Returns:
        저장된 영상 파일 경로
    """
    os.makedirs(save_dir, exist_ok=True)

    filename = f"{safe_filename(code)}.mp4"
    save_path = os.path.join(save_dir, filename)

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(
        video_url,
        headers=headers,
        stream=True,
        timeout=60
    )

    response.raise_for_status()

    with open(save_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)

    return save_path

def download_top_reel_videos(top_reels: list[dict], save_dir: str = "videos") -> list[dict]:
    """
    Top 릴스 목록의 video_url을 이용해 영상을 다운로드하고,
    각 릴스 dict에 local_video_path를 추가한다.
    """
    downloaded = []

    for reel in top_reels:
        video_url = reel.get("video_url")
        code = reel.get("code") or reel.get("id")

        if not video_url:
            print(f"[건너뜀] video_url 없음: {code}")
            continue

        try:
            video_path = download_reel_video(
                video_url=video_url,
                code=code,
                save_dir=save_dir
            )

            reel["local_video_path"] = video_path
            downloaded.append(reel)

            print(f"[다운로드 완료] {code} -> {video_path}")

        except Exception as e:
            print(f"[다운로드 실패] {code}: {e}")

    return downloaded

# 3. 메인 실행부
if __name__ == "__main__":
    keyword = "성수동 카페 인테리어"

    top_reels = get_top_reels(
        keyword=keyword,
        max_items=20,
        top_n=5
    )

    if not top_reels:
        print("수집된 릴스가 없습니다.")
    else:
        print("\n=== 상위 릴스 결과 ===")

        df = pd.DataFrame(top_reels)
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

        print("\n=== 영상 다운로드 시작 ===")
        downloaded_reels = download_top_reel_videos(
            top_reels,
            save_dir="videos"
        )

        print(f"\n총 {len(downloaded_reels)}개 영상 다운로드 완료")

        print("\n=== 필터링된 릴스 캡션 확인 ===")
        
        for reel in top_reels:
            print("URL:", reel["url"])
            print("점수:", reel["rank_score"])
            print("캡션:", reel["caption"][:100])
            print("-" * 50)