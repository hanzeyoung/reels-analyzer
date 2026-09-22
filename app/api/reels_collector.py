# reels_collector.py

import os
import math
import time
import argparse
from pathlib import Path

import json
import re
from datetime import datetime
from difflib import SequenceMatcher

import requests
import pandas as pd
from dotenv import load_dotenv

from app.core.config import get_env, require_env
from app.core.observability import enforce_daily_limit, observed_operation, record_api_usage

# 1. 환경 변수 로드
load_dotenv()

# 2. Apify 설정
APIFY_TOKEN = get_env("APIFY_TOKEN")
ACTOR_ID = "patient_discovery/instagram-search-reels"
DOWNLOAD_LOG_FILENAME = "download_log.jsonl"
KEYWORD_CATEGORY_SUFFIXES = [
    "베이커리", "디저트", "브런치", "필라테스", "헬스", "맛집", "카페",
    "식당", "식사", "음식", "외식", "밥집", "네일", "뷰티", "패션", "미용",
    "술집", "병원", "학원", "공방",
]
LOCATION_SUFFIXES = ["동", "역", "구", "시", "군", "읍", "면", "리", "로", "길", "가"]
CATEGORY_ALIASES = {
    "카페": ["카페", "커피", "라떼", "디저트", "베이커리", "브런치", "빵집", "소금빵", "수플레", "타르트", "팬케이크", "휘낭시에", "에그타르트", "까눌레", "말차"],
    "맛집": ["맛집", "음식", "메뉴", "식당", "밥집", "고기", "파스타", "라멘", "국밥", "분식", "한식", "일식", "양식"],
    "식사": ["식사", "외식", "맛집", "음식", "메뉴", "식당", "밥집", "고기", "파스타", "라멘", "국밥", "분식", "한식", "일식", "양식"],
    "음식": ["음식", "식사", "외식", "맛집", "메뉴", "식당", "밥집", "고기", "파스타", "라멘", "국밥", "분식", "한식", "일식", "양식"],
    "외식": ["외식", "식사", "맛집", "음식", "메뉴", "식당", "밥집"],
    "밥집": ["밥집", "맛집", "음식", "식사", "메뉴", "식당", "국밥", "한식"],
    "네일": ["네일", "네일샵", "네일아트", "젤네일", "패디", "손톱"],
    "뷰티": ["뷰티", "미용", "메이크업", "피부", "관리", "왁싱", "속눈썹"],
    "헬스": ["헬스", "운동", "피트니스", "pt", "근력", "다이어트"],
    "필라테스": ["필라테스", "운동", "체형", "자세", "재활"],
}

def get_reels_data(keyword: str, max_items: int = 20) -> list[dict]:
    """
    Apify REST API를 직접 호출해서 검색어 기반 릴스 데이터를 가져온다.
    apify-client의 Pydantic 검증 오류를 우회하기 위한 방식.
    """
    run_input = {
        "query": keyword,
        "maxItems": max_items,
    }

    enforce_daily_limit("apify", max_calls=int(get_env("APIFY_DAILY_CALL_LIMIT", "50") or 50))
    apify_token = require_env("APIFY_TOKEN", "Apify 릴스 수집")
    headers = {
        "Authorization": f"Bearer {apify_token}",
        "Content-Type": "application/json",
    }

    # Actor ID는 URL에서 / 대신 ~ 사용
    actor_id_for_url = ACTOR_ID.replace("/", "~")

    # 1. Actor 실행
    start_url = f"https://api.apify.com/v2/acts/{actor_id_for_url}/runs"

    with observed_operation("apify.reels_collection", keyword=keyword, max_items=max_items):
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

    result = dataset_res.json()
    record_api_usage("apify", metadata={"operation": "reels_collection", "items": len(result)})
    return result

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

def strip_hashtags(value: str) -> str:
    """해시태그만 맞는 결과가 주제 일치로 과대평가되지 않도록 제거합니다."""
    return re.sub(r"#[0-9a-zA-Z가-힣_]+", " ", str(value or ""))

def get_category_aliases(category_terms: list[str]) -> list[str]:
    aliases = []
    for term in category_terms:
        aliases.extend(CATEGORY_ALIASES.get(term, [term]))
    return list(dict.fromkeys(normalize_search_text(alias) for alias in aliases if alias))

def match_any_term(terms: list[str], text: str, compact_text: str) -> list[str]:
    return [
        term for term in terms
        if term and (term in text or compact_search_text(term) in compact_text)
    ]

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

def expand_keyword_terms(keyword: str) -> list[str]:
    """붙여 쓴 검색어를 지역/업종 단어로 확장합니다. 예: 성수동카페 -> 성수동, 성수, 카페."""
    terms = []
    for raw_term in normalize_search_text(keyword).split(" "):
        term = raw_term.strip()
        if not term:
            continue

        terms.append(term)
        compact = compact_search_text(term)

        for suffix in sorted(KEYWORD_CATEGORY_SUFFIXES, key=len, reverse=True):
            if compact.endswith(suffix) and len(compact) > len(suffix):
                location = compact[:-len(suffix)]
                terms.extend([location, suffix])
                if len(location) > 2 and location[-1] in LOCATION_SUFFIXES:
                    terms.append(location[:-1])
                break

    return list(dict.fromkeys(term for term in terms if len(term) >= 2))

def get_keyword_terms(keyword: str) -> list[str]:
    """복합 검색어를 관련성 검증용 단어 목록으로 분해합니다."""
    return expand_keyword_terms(keyword)

def calculate_keyword_relevance(item, keyword: str) -> tuple[bool, float, list[str]]:
    """검색어와 실제 릴스 메타데이터의 관련성을 점수화합니다."""
    if not keyword:
        return True, 1.0, []

    keyword_text = normalize_search_text(keyword)
    keyword_compact = compact_search_text(keyword)
    if not keyword_text:
        return True, 1.0, []

    caption_text = get_caption_text(item)
    primary_text = " ".join(filter(None, [strip_hashtags(caption_text), get_audio_title(item)]))
    full_text = get_relevance_text(item)
    primary_search_text = normalize_search_text(primary_text)
    primary_compact = compact_search_text(primary_text)
    full_search_text = normalize_search_text(full_text)
    full_compact = compact_search_text(full_text)

    terms = get_keyword_terms(keyword)
    if not terms:
        return True, 1.0, []

    original_compact = keyword_compact
    core_terms = [term for term in terms if term != original_compact]
    if not core_terms:
        is_match = original_compact in full_compact
        score = 1.0 if original_compact in primary_compact else 0.65
        return is_match, score if is_match else 0.0, [original_compact] if is_match else []

    category_terms = [term for term in core_terms if term in KEYWORD_CATEGORY_SUFFIXES]
    location_terms = [term for term in core_terms if term not in KEYWORD_CATEGORY_SUFFIXES]
    category_aliases = get_category_aliases(category_terms)

    matched_locations_primary = match_any_term(location_terms, primary_search_text, primary_compact)
    matched_locations_full = match_any_term(location_terms, full_search_text, full_compact)
    matched_categories_primary = match_any_term(category_aliases, primary_search_text, primary_compact)
    matched_categories_full = match_any_term(category_aliases, full_search_text, full_compact)

    full_exact_primary = keyword_text in primary_search_text or keyword_compact in primary_compact
    full_exact_any = keyword_text in full_search_text or keyword_compact in full_compact

    if category_terms and location_terms:
        is_match = bool(full_exact_primary or (matched_locations_primary and matched_categories_primary))
    elif category_terms:
        is_match = bool(matched_categories_primary or full_exact_primary)
    elif location_terms:
        is_match = bool(matched_locations_primary or full_exact_primary)
    else:
        matched_core = match_any_term(core_terms, full_search_text, full_compact)
        required_count = len(core_terms) if len(core_terms) <= 3 else math.ceil(len(core_terms) * 0.75)
        is_match = len(set(matched_core)) >= required_count

    if not is_match:
        return False, 0.0, []

    matched_terms = []
    if full_exact_any:
        matched_terms.append(original_compact)
    matched_terms.extend(matched_locations_primary or matched_locations_full)
    matched_terms.extend(matched_categories_primary or matched_categories_full)
    matched_terms = list(dict.fromkeys(matched_terms))

    if full_exact_primary:
        score = 1.0
    elif matched_locations_primary and matched_categories_primary:
        score = 0.92
    elif matched_categories_primary or matched_locations_primary:
        score = 0.72
    elif matched_categories_full or matched_locations_full:
        score = 0.72
    else:
        score = 0.65

    return True, round(score, 4), matched_terms

def is_relevant_reel(item, keyword):
    """검색어와 실제 릴스 메타데이터가 맞는 경우에만 통과시킵니다."""
    is_match, _, _ = calculate_keyword_relevance(item, keyword)
    return is_match

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

    for reel in sorted(
        reels,
        key=lambda x: (x.get("keyword_relevance_score", 0), x["rank_score"]),
        reverse=True,
    ):
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
        is_relevant, relevance_score, matched_terms = calculate_keyword_relevance(reel, keyword)
        if not is_relevant:
            code = reel.get("code") or reel.get("id") or "unknown"
            print(f"[키워드 무관 제외] {code} · 검색어={keyword}")
            continue

        user = reel.get("user", {})
        if not isinstance(user, dict):
            user = {}

        processed.append({
            "rank_score": calculate_score(reel),
            "keyword_relevance_score": relevance_score,
            "matched_keyword_terms": matched_terms,
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
    keyword = str(keyword or "").strip()
    if not keyword:
        raise ValueError("검색 키워드를 입력해주세요.")
    previous_reels = sync_existing_videos_to_log(save_dir) if save_dir else []
    candidate_count = max(max_items, top_n * candidate_multiplier)
    max_candidate_count = max(candidate_count, top_n * 12)
    top_reels = []

    while candidate_count <= max_candidate_count:
        raw_data = get_reels_data(keyword, max_items=candidate_count)
        processed = process_reels(raw_data, keyword)
        top_reels = select_unique_top_reels(processed, top_n, previous_reels=previous_reels)

        print(
            f"[키워드 필터] 후보 {len(raw_data)}개 중 관련 영상 {len(processed)}개, "
            f"선택 {len(top_reels)}/{top_n}개"
        )
        if len(top_reels) >= top_n:
            break

        # 일부 Actor는 요청 수보다 적은 고정 개수만 반환합니다. 이 경우 더 큰
        # 요청을 반복해도 같은 결과만 오므로 현재 결과를 즉시 사용자에게 보여줍니다.
        if len(raw_data) < candidate_count:
            print(f"[키워드 필터] Actor가 요청 {candidate_count}개보다 적은 {len(raw_data)}개를 반환해 추가 호출을 생략합니다.")
            break

        next_candidate_count = min(candidate_count * 2, max_candidate_count)
        if next_candidate_count == candidate_count:
            break
        candidate_count = next_candidate_count

    if len(top_reels) < top_n:
        print(f"[경고] 키워드와 관련 있고 중복이 아닌 릴스를 {len(top_reels)}/{top_n}개만 찾았습니다.")

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
        "keyword_relevance_score": reel.get("keyword_relevance_score"),
        "matched_keyword_terms": reel.get("matched_keyword_terms", []),
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

def download_top_reel_videos(
    top_reels: list[dict],
    save_dir: str = "videos",
    keyword: str = "",
    target_count: int | None = None,
) -> list[dict]:
    """
    Top 릴스 목록의 video_url을 이용해 영상을 다운로드하고,
    각 릴스 dict에 local_video_path를 추가한다.
    keyword가 있으면 다운로드 직전에도 관련성 검사를 한 번 더 수행한다.
    """
    downloaded = []
    download_log = sync_existing_videos_to_log(save_dir)
    target_count = target_count or len(top_reels)

    for reel in top_reels:
        video_url = reel.get("video_url")
        code = reel.get("code") or reel.get("id")

        if not video_url:
            print(f"[건너뜀] video_url 없음: {code}")
            continue

        if keyword:
            is_relevant, relevance_score, matched_terms = calculate_keyword_relevance(reel, keyword)
            if not is_relevant:
                print(f"[키워드 무관 다운로드 제외] {code} · 검색어={keyword}")
                continue
            reel["keyword_relevance_score"] = relevance_score
            reel["matched_keyword_terms"] = matched_terms

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
            reel["local_video_path"] = save_path
            downloaded.append(reel)
            if len(downloaded) >= target_count:
                break
            continue
        if is_duplicate_reel(reel, download_log):
            print(f"[로그 중복 건너뜀] {code}")
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
            if len(downloaded) >= target_count:
                break

        except Exception as e:
            print(f"[다운로드 실패] {code}: {e}")

    return downloaded

# 3. 메인 실행부
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="인스타그램 릴스 검색어를 입력해 상위 릴스를 수집합니다.")
    parser.add_argument("--keyword", default="", help="검색 키워드. 예: 성수동카페, 강남네일, 홍대맛집")
    parser.add_argument("--max-items", type=int, default=20, help="Apify에서 가져올 후보 릴스 수")
    parser.add_argument("--top-n", type=int, default=5, help="스코어링 후 다운로드할 상위 릴스 수")
    parser.add_argument("--save-dir", default="videos", help="영상과 다운로드 로그를 저장할 폴더")
    args = parser.parse_args()

    keyword = args.keyword.strip()
    if not keyword:
        keyword = input("검색 키워드를 입력하세요 (예: 성수동카페): ").strip()

    if not keyword:
        raise ValueError("검색 키워드가 필요합니다.")

    top_reels = get_top_reels(
        keyword=keyword,
        max_items=args.max_items,
        top_n=args.top_n * 3,
        save_dir=args.save_dir
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
            "keyword_relevance_score",
            "matched_keyword_terms",
            "video_url"
        ]])

        print("\n=== 영상 다운로드 시작 ===")
        downloaded_reels = download_top_reel_videos(
            top_reels,
            save_dir=args.save_dir,
            keyword=keyword,
            target_count=args.top_n,
        )

        print(f"\n총 {len(downloaded_reels)}개 영상 다운로드 완료")
        if len(downloaded_reels) < args.top_n:
            raise RuntimeError(f"키워드 관련 영상 {args.top_n}개 확보 실패: {len(downloaded_reels)}개만 확보됨")

        print("\n=== 필터링된 릴스 캡션 확인 ===")

        for reel in top_reels:
            print("URL:", reel["url"])
            print("점수:", reel["rank_score"])
            print("매칭 키워드:", ", ".join(reel.get("matched_keyword_terms", [])))
            print("관련성 점수:", reel.get("keyword_relevance_score"))
            print("캡션:", reel["caption"][:100])
            print("-" * 50)
