# reels_collector.py

import os
import math
import time
from pathlib import Path

import json
import re
from datetime import datetime
from difflib import SequenceMatcher

import requests
import pandas as pd
from dotenv import load_dotenv

# 1. 환경 변수 로드
load_dotenv()

# 2. Apify 설정
APIFY_TOKEN = os.getenv("APIFY_TOKEN")
ACTOR_ID = "patient_discovery/instagram-search-reels"
DOWNLOAD_LOG_FILENAME = "download_log.jsonl"

if not APIFY_TOKEN:
    raise ValueError("APIFY_TOKEN이 없습니다. .env 파일을 확인하세요.")


def get_reels_data(keyword: str, max_items: int = 20) -> list[dict]:
    """
    Apify REST API를 직접 호출해서 검색어 기반 릴스 데이터를 가져온다.
    apify-client의 Pydantic 검증 오류를 우회하기 위한 방식.
    """
    run_input = {
        "query": keyword,
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


def calculate_score(item):
    """기존 Buza 점수 계산 로직을 재사용합니다."""
    return calculate_buza_score(item)


def safe_number(value):
    """숫자형이 아니거나 None인 경우 0을 반환합니다."""
    if value is None:
        return 0
    try:
        return int(value)
    except (ValueError, TypeError):
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0


def get_caption_text(item):
    """릴스 캡션을 안전하게 추출합니다."""
    caption = item.get("caption") or item.get("caption_text") or item.get("description") or ""
    if isinstance(caption, dict):
        caption = caption.get("text") or caption.get("caption_text") or caption.get("description") or ""
    if isinstance(caption, list):
        caption = " ".join(str(v) for v in caption)
    return str(caption)


def get_audio_title(item):
    """오디오 제목을 안전하게 추출합니다."""
    return str(item.get("audio_title") or item.get("music_title") or item.get("audio_name") or "")


def normalize_search_text(value: str) -> str:
    """검색 비교용 텍스트를 소문자와 공백 기준으로 정리합니다."""
    text = str(value or "").lower()
    text = re.sub(r"[^0-9a-z가-힣]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compact_search_text(value: str) -> str:
    """해시태그처럼 붙어 있는 키워드 비교를 위해 공백을 제거합니다."""
    return normalize_search_text(value).replace(" ", "")


def get_relevance_text(item) -> str:
    """키워드 관련성 판단에 쓸 사용자 노출 메타데이터만 모읍니다."""
    user = item.get("user") or {}
    if not isinstance(user, dict):
        user = {}

    location = item.get("location") or {}
    if not isinstance(location, dict):
        location = {"name": str(location)}

    caption = item.get("caption") or {}
    if not isinstance(caption, dict):
        caption = {}

    hashtags = item.get("hashtags") or item.get("tags") or caption.get("hashtags") or []
    if isinstance(hashtags, list):
        hashtags = " ".join(str(tag) for tag in hashtags)

    return " ".join(filter(None, [
        get_caption_text(item),
        hashtags,
        user.get("username", ""),
        user.get("userName", ""),
        user.get("full_name", ""),
        user.get("fullName", ""),
        (caption.get("user") or {}).get("username", "") if isinstance(caption.get("user"), dict) else "",
        (caption.get("user") or {}).get("full_name", "") if isinstance(caption.get("user"), dict) else "",
        item.get("owner_username", ""),
        item.get("ownerUsername", ""),
        item.get("owner_full_name", ""),
        item.get("ownerFullName", ""),
        item.get("username", ""),
        item.get("full_name", ""),
        item.get("fullName", ""),
        location.get("name", ""),
        location.get("city", ""),
        item.get("location_name", ""),
        item.get("locationName", ""),
    ]))


def get_keyword_terms(keyword: str) -> list[str]:
    """복합 검색어를 관련성 검증용 단어 목록으로 분해합니다."""
    normalized = normalize_search_text(keyword)
    return list(dict.fromkeys(term for term in normalized.split(" ") if term))


def is_relevant_reel(item, keyword):
    """검색어와 실제 릴스 메타데이터가 맞는 경우에만 통과시킵니다."""
    if not keyword:
        return True

    relevance_text = get_relevance_text(item)
    keyword_text = normalize_search_text(keyword)
    keyword_compact = compact_search_text(keyword)
    search_text = normalize_search_text(relevance_text)
    search_compact = compact_search_text(relevance_text)

    if not keyword_text:
        return True

    # 전체 문구가 그대로 있거나 해시태그처럼 붙어 있으면 가장 확실한 관련 결과입니다.
    if keyword_text in search_text or keyword_compact in search_compact:
        return True

    terms = get_keyword_terms(keyword)
    if not terms:
        return True

    matched_count = sum(
        1 for term in terms
        if term in search_text or term in search_compact
    )

    if len(terms) == 1:
        return matched_count == 1

    required_count = len(terms) if len(terms) <= 3 else math.ceil(len(terms) * 0.75)
    return matched_count >= required_count


def normalize_duplicate_text(value: str) -> str:
    """중복 릴스 비교용으로 캡션을 정규화합니다."""
    text = normalize_search_text(value)
    tokens = [
        token for token in text.split()
        if not token.startswith("http") and token not in {"reels", "reel", "릴스"}
    ]
    return " ".join(tokens)


def get_reel_identity(reel: dict) -> tuple[str, ...]:
    """완전히 같은 릴스를 빠르게 찾기 위한 고유값 후보를 반환합니다."""
    return tuple(
        str(value)
        for value in [
            reel.get("id"),
            reel.get("code"),
            reel.get("url"),
            reel.get("video_url"),
        ]
        if value
    )


def is_duplicate_reel(candidate: dict, selected: list[dict], caption_threshold: float = 0.82) -> bool:
    """이미 선택된 릴스와 같거나 거의 같은 콘텐츠인지 판단합니다."""
    candidate_identity = set(get_reel_identity(candidate))
    candidate_caption = normalize_duplicate_text(candidate.get("caption", ""))

    for reel in selected:
        if candidate_identity.intersection(get_reel_identity(reel)):
            return True

        selected_caption = normalize_duplicate_text(reel.get("caption", ""))
        if not candidate_caption or not selected_caption:
            continue

        short_len = min(len(candidate_caption), len(selected_caption))
        if short_len < 40:
            continue

        if candidate_caption[:80] == selected_caption[:80]:
            return True

        similarity = SequenceMatcher(None, candidate_caption, selected_caption).ratio()
        if similarity >= caption_threshold:
            return True

    return False


def select_unique_top_reels(
    reels: list[dict],
    top_n: int,
    previous_reels: list[dict] | None = None,
) -> list[dict]:
    """성과 점수 상위 릴스 중 중복/유사 콘텐츠를 제외하고 선택합니다."""
    selected = []
    previous_reels = previous_reels or []

    for reel in sorted(reels, key=lambda x: x["rank_score"], reverse=True):
        if is_duplicate_reel(reel, previous_reels):
            print(f"[로그 중복 제외] {reel.get('code') or reel.get('id')}")
            continue

        if is_duplicate_reel(reel, selected):
            print(f"[중복 제외] {reel.get('code') or reel.get('id')}")
            continue

        selected.append(reel)
        if len(selected) >= top_n:
            break

    return selected


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

def get_top_reels(
    keyword: str,
    max_items: int = 20,
    top_n: int = 5,
    save_dir: str | None = None,
    candidate_multiplier: int = 3,
) -> list[dict]:
    candidate_count = max(max_items, top_n * candidate_multiplier)
    raw_data = get_reels_data(keyword, max_items=candidate_count)
    processed = process_reels(raw_data, keyword)
    previous_reels = sync_existing_videos_to_log(save_dir) if save_dir else []

    top_reels = select_unique_top_reels(processed, top_n, previous_reels=previous_reels)

    return top_reels

def safe_filename(text: str) -> str:
    """
    파일명에 쓸 수 없는 문자를 제거한다.
    """
    if not text:
        return "unknown"

    return re.sub(r'[\\/:*?"<>|]', "_", text)


def get_video_save_path(code: str, save_dir: str = "videos") -> str:
    """릴스 code 기준 저장 경로를 반환합니다."""
    filename = f"{safe_filename(code)}.mp4"
    return os.path.join(save_dir, filename)


def get_download_log_path(save_dir: str = "videos") -> str:
    """다운로드 로그 파일 경로를 반환합니다."""
    return os.path.join(save_dir, DOWNLOAD_LOG_FILENAME)


def read_download_log(save_dir: str = "videos") -> list[dict]:
    """videos 폴더의 다운로드 로그를 읽어 중복 비교용 목록으로 반환합니다."""
    log_path = get_download_log_path(save_dir)
    if not os.path.exists(log_path):
        return []

    entries = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return entries


def append_download_log(
    reel: dict,
    video_path: str,
    save_dir: str = "videos",
    status: str = "downloaded",
    downloaded_at: str | None = None,
) -> dict:
    """다운로드된 릴스 정보를 JSON Lines 로그에 추가합니다."""
    os.makedirs(save_dir, exist_ok=True)

    code = reel.get("code") or reel.get("id")
    downloaded_at = downloaded_at or datetime.now().astimezone().isoformat(timespec="seconds")
    entry = {
        "downloaded_at": downloaded_at,
        "status": status,
        "code": code,
        "id": reel.get("id"),
        "url": reel.get("url"),
        "username": reel.get("username"),
        "rank_score": reel.get("rank_score"),
        "caption": reel.get("caption", ""),
        "caption_normalized": normalize_duplicate_text(reel.get("caption", "")),
        "ig_play_count": reel.get("ig_play_count"),
        "like_count": reel.get("like_count"),
        "comment_count": reel.get("comment_count"),
        "share_count": reel.get("share_count"),
        "video_url": reel.get("video_url"),
        "local_video_path": video_path,
        "message": f"[다운로드 완료] {code} -> {video_path}",
    }

    with open(get_download_log_path(save_dir), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return entry


def sync_existing_videos_to_log(save_dir: str = "videos") -> list[dict]:
    """로그가 없는 기존 mp4도 code 기준 중복 비교에 쓰도록 로그에 반영합니다."""
    os.makedirs(save_dir, exist_ok=True)

    entries = read_download_log(save_dir)
    logged_codes = {str(entry.get("code")) for entry in entries if entry.get("code")}

    for video_file in Path(save_dir).glob("*.mp4"):
        code = video_file.stem
        if code in logged_codes:
            continue

        downloaded_at = datetime.fromtimestamp(
            video_file.stat().st_mtime
        ).astimezone().isoformat(timespec="seconds")
        entry = append_download_log(
            {
                "code": code,
                "id": code,
                "url": f"https://www.instagram.com/reel/{code}/",
                "caption": "",
            },
            video_path=str(video_file),
            save_dir=save_dir,
            status="existing_file",
            downloaded_at=downloaded_at,
        )
        entries.append(entry)
        logged_codes.add(code)

    return entries


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

    save_path = get_video_save_path(code, save_dir)

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
    download_log = sync_existing_videos_to_log(save_dir)

    for reel in top_reels:
        video_url = reel.get("video_url")
        code = reel.get("code") or reel.get("id")

        if not video_url:
            print(f"[건너뜀] video_url 없음: {code}")
            continue

        if is_duplicate_reel(reel, download_log):
            print(f"[로그 중복 건너뜀] {code}")
            continue

        save_path = get_video_save_path(code, save_dir)
        if os.path.exists(save_path):
            log_entry = append_download_log(
                reel,
                video_path=save_path,
                save_dir=save_dir,
                status="existing_file",
            )
            download_log.append(log_entry)
            print(f"[기존 파일 건너뜀] {code} -> {save_path}")
            continue

        try:
            video_path = download_reel_video(
                video_url=video_url,
                code=code,
                save_dir=save_dir
            )

            reel["local_video_path"] = video_path
            downloaded.append(reel)
            download_log.append(append_download_log(reel, video_path, save_dir=save_dir))

            print(f"[다운로드 완료] {code} -> {video_path}")

        except Exception as e:
            print(f"[다운로드 실패] {code}: {e}")

    return downloaded

# 3. 메인 실행부
if __name__ == "__main__":
    keyword = "성수동카페"

    top_reels = get_top_reels(
        keyword=keyword,
        max_items=20,
        top_n=5,
        save_dir="videos"
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
