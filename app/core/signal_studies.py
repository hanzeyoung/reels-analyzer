"""Persistent multi-reel studies used to turn market signals into one project brief."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median


STOP_WORDS = {
    "그리고", "하지만", "오늘", "이번", "정말", "너무", "있는", "합니다", "이거", "여기",
    "요즘", "무조건", "진짜", "완전", "바로", "우리", "제가", "저희", "영상", "릴스",
    "메뉴", "맛집", "카페", "추천", "방문", "소개", "사람", "정도", "때문", "같은",
    "the", "and", "with", "this", "that", "from", "for", "your", "reel",
}

PATTERN_DEFINITIONS = (
    {
        "id": "authenticity", "label": "직접 만드는 전문성",
        "terms": ("셰프", "직접", "수제", "현지", "정통", "전문", "원재료", "유기농", "숙성", "본연"),
        "why": "말로 주장하기보다 만드는 사람과 재료를 보여줄 때 신뢰가 생깁니다.",
        "hook": "{focus}, 직접 만드는 장면부터 보여드립니다",
        "shots": (
            ("close", "핵심 재료와 만드는 손을 한 화면에 담기", "손·재료 클로즈업", "{focus}, 직접 만드는 이유"),
            ("person", "만드는 사람의 얼굴과 작업 공간을 연결하기", "눈높이 미디엄샷", "누가 어떻게 만드는지 보여드릴게요"),
        ),
    },
    {
        "id": "atmosphere", "label": "공간과 분위기",
        "terms": ("공간", "인테리어", "분위기", "우드톤", "층고", "햇살", "감성", "오션뷰", "시티뷰", "데이트", "창가", "좌석", "여행"),
        "why": "공간의 첫인상과 머무는 이유를 한 흐름으로 보여줄 수 있습니다.",
        "hook": "{focus}, 들어서는 순간 분위기가 달라집니다",
        "shots": (
            ("space", "입구에서 대표 좌석까지 공간의 흐름 보여주기", "와이드 워킹샷", "들어오자마자 보이는 이 분위기"),
            ("space", "빛·좌석·소품 중 반복 근거가 보이는 지점 담기", "고정 와이드샷", "머물고 싶은 이유는 공간에도 있어요"),
        ),
    },
    {
        "id": "value", "label": "가격과 구성의 이점",
        "terms": ("가격", "가성비", "만원", "천원", "원대", "저렴", "무제한", "세트", "구성", "혜택"),
        "why": "가격표와 실제 구성을 함께 보여주면 가치가 즉시 이해됩니다.",
        "hook": "{focus}, 이 구성이라면 가격부터 확인하세요",
        "shots": (
            ("hero", "전체 구성과 가격 정보를 한 화면에 제시하기", "탑뷰 또는 정면샷", "이 구성이 한 번에 나옵니다"),
            ("close", "구성품을 하나씩 짧게 짚어 실제 양 증명하기", "빠른 클로즈업", "가격보다 먼저 봐야 할 구성"),
        ),
    },
    {
        "id": "sensory", "label": "메뉴 디테일과 감각",
        "terms": ("단면", "질감", "바삭", "꾸덕", "촉촉", "향기", "재료", "플레이팅", "크림", "육즙", "소스", "식감", "비주얼"),
        "why": "가까운 화면과 움직임으로 맛과 질감을 대신 전달할 수 있습니다.",
        "hook": "{focus}, 이 디테일은 가까이서 봐야 합니다",
        "shots": (
            ("close", "자르거나 떠올리는 순간의 단면과 질감 담기", "매크로 클로즈업", "이 단면과 질감을 보세요"),
            ("hand", "붓기·자르기·집기 중 핵심 동작을 한 번에 촬영하기", "손 팔로잉샷", "완성되는 순간이 가장 맛있어 보여요"),
        ),
    },
    {
        "id": "scarcity", "label": "희소성과 행동 이유",
        "terms": ("웨이팅", "한정", "예약", "품절", "오픈런", "마감", "선착순", "기간", "자리"),
        "why": "언제 어떻게 방문해야 하는지 구체적으로 알려 행동을 돕습니다.",
        "hook": "{focus}, 놓치기 전에 먼저 확인하세요",
        "shots": (
            ("hero", "한정 대상이나 대기 현황을 첫 장면에 제시하기", "고정 정면샷", "놓치기 전에 확인할 한 가지"),
            ("space", "입구·예약 화면·운영 시간을 차례로 담기", "짧은 고정샷", "방문 전 이 정보는 저장하세요"),
        ),
    },
    {
        "id": "problem_solution", "label": "선택 고민 해결",
        "terms": ("고민", "실패", "찾는다면", "고르", "선택", "어디", "모르", "해결", "취향"),
        "why": "시청자의 선택 고민을 먼저 말하면 추천의 이유가 선명해집니다.",
        "hook": "{focus} 고르기 어렵다면 이 기준부터 보세요",
        "shots": (
            ("person", "손님이 고민하는 상황을 짧게 재현하기", "눈높이 정면샷", "이런 곳 찾느라 고민했다면"),
            ("hero", "선택 기준이 되는 대표 결과를 바로 제시하기", "대표 장면 클로즈업", "선택 기준은 바로 이 장면입니다"),
        ),
    },
    {
        "id": "transformation", "label": "전후 변화와 결과",
        "terms": ("전후", "비포", "애프터", "변화", "달라", "개선", "완성", "결과", "효과"),
        "why": "시작과 결과를 같은 구도로 비교하면 변화가 즉시 이해됩니다.",
        "hook": "{focus}, 전과 후를 먼저 비교해보세요",
        "shots": (
            ("person", "변화 전 상태를 기준 구도로 짧게 기록하기", "고정 정면샷", "시작은 이랬습니다"),
            ("hero", "같은 위치와 크기로 완성 결과 비교하기", "동일 구도 매치컷", "같은 구도에서 보면 차이가 보입니다"),
        ),
    },
    {
        "id": "process", "label": "과정과 사용 방법",
        "terms": ("과정", "순서", "단계", "방법", "사용", "바르", "시술", "만들", "준비", "팁"),
        "why": "핵심 과정을 순서대로 보여주면 따라 할 수 있고 전문성도 드러납니다.",
        "hook": "{focus}, 결과를 만드는 핵심 과정부터 보세요",
        "shots": (
            ("hand", "가장 중요한 동작을 손 중심으로 한 번에 보여주기", "손 팔로잉샷", "결과를 가르는 핵심 동작"),
            ("close", "도구와 대상이 만나는 지점을 가까이 담기", "디테일 클로즈업", "이 단계에서 차이가 생깁니다"),
        ),
    },
    {
        "id": "social_proof", "label": "후기와 인기 근거",
        "terms": ("후기", "리뷰", "인기", "주문", "재방문", "고객", "입소문", "베스트"),
        "why": "실제 선택 장면과 반응을 보여주면 인기라는 말을 증거로 바꿀 수 있습니다.",
        "hook": "{focus}, 사람들이 반복해서 고르는 장면을 보세요",
        "shots": (
            ("person", "손님이 실제로 선택하거나 반응하는 순간 담기", "눈높이 관찰샷", "반복해서 선택되는 이유"),
            ("hero", "가장 많이 선택된 결과를 단독으로 보여주기", "대표 장면 정면샷", "가장 많이 찾는 결과는 이것입니다"),
        ),
    },
)

PATTERN_SPECIFICITY = {
    "atmosphere": 2,
    "authenticity": 3,
    "value": 3,
    "sensory": 3,
    "scarcity": 3,
    "problem_solution": 3,
    "transformation": 4,
    "process": 3,
    "social_proof": 3,
}


def _read(path: str | Path) -> dict:
    target = Path(path)
    if not target.exists():
        return {"items": [], "updated_at": ""}
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"items": [], "updated_at": ""}
    except (OSError, json.JSONDecodeError):
        return {"items": [], "updated_at": ""}


def _write(study: dict, path: str | Path) -> dict:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {**study, "updated_at": datetime.now().astimezone().isoformat(timespec="seconds")}
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    return payload


def load_study(path: str | Path) -> dict:
    study = _read(path)
    items = study.get("items")
    return {**study, "items": items if isinstance(items, list) else []}



def replace_signals(signals: list[dict], path: str | Path, query: str = "") -> dict:
    """Replace the current study with every unique signal from one Radar search."""
    unique = []
    seen = set()
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        identity = str(signal.get("media_id") or signal.get("url") or "")
        if not identity or identity in seen:
            continue
        seen.add(identity)
        unique.append(signal)
    return _write({"items": unique, "visual_analyses": {}, "query": str(query or "")}, path)


def add_signal(signal: dict, path: str | Path) -> dict:
    study = load_study(path)
    identity = str(signal.get("media_id") or signal.get("url") or "")
    if not identity:
        raise ValueError("신호에 media_id 또는 원본 URL이 필요합니다.")
    items = [item for item in study["items"] if str(item.get("media_id") or item.get("url") or "") != identity]
    items.append(signal)
    return _write({**study, "items": items}, path)


def remove_signal(identity: str, path: str | Path) -> dict:
    study = load_study(path)
    items = [
        item for item in study["items"]
        if str(item.get("media_id") or item.get("url") or "") != str(identity)
    ]
    return _write({**study, "items": items}, path)


def save_visual_analysis(analyses: dict[str, dict], path: str | Path) -> dict:
    """Persist per-reel visual evidence after an explicit user-triggered AI run."""
    study = load_study(path)
    return _write({**study, "visual_analyses": analyses}, path)


def _first_line(value: str) -> str:
    return next((line.strip() for line in str(value or "").splitlines() if line.strip()), "")


def _normalize_term(word: str) -> str:
    value = word.lower().lstrip("#")
    for suffix in ("에서는", "으로는", "이라는", "에서", "으로", "처럼", "보다", "까지", "부터", "인데", "에는", "하고", "이며", "은", "는", "이", "가", "을", "를", "의", "에", "도", "만"):
        if value.endswith(suffix) and len(value) - len(suffix) >= 2:
            value = value[:-len(suffix)]
            break
    return value


def _terms(caption: str) -> list[str]:
    values = [_normalize_term(word) for word in re.findall(r"[A-Za-z가-힣]{2,}", str(caption or ""))]
    return [word for word in values if word and word not in STOP_WORDS]


def _evidence_excerpt(caption: str, triggers: list[str], limit: int = 90) -> str:
    text = re.sub(r"\s+", " ", str(caption or "")).strip()
    if not text:
        return ""
    lowered = text.lower()
    positions = [lowered.find(trigger.lower()) for trigger in triggers if lowered.find(trigger.lower()) >= 0]
    start = max(0, (min(positions) if positions else 0) - 24)
    excerpt = text[start:start + limit]
    return ("…" if start else "") + excerpt + ("…" if start + limit < len(text) else "")


def _common_patterns(selected: list[dict], threshold: int) -> list[dict]:
    patterns = []
    for definition in PATTERN_DEFINITIONS:
        evidence = []
        all_matches = set()
        for item in selected:
            caption = str(item.get("caption") or "")
            lowered = caption.lower()
            matches = sorted({term for term in definition["terms"] if term in lowered})
            if not matches:
                continue
            all_matches.update(matches)
            evidence.append({
                "media_id": str(item.get("media_id") or ""),
                "username": str(item.get("username") or ""),
                "url": str(item.get("url") or ""),
                "thumbnail_url": str(item.get("thumbnail_url") or ""),
                "matches": matches,
                "excerpt": _evidence_excerpt(caption, matches),
            })
        if len(evidence) >= threshold:
            patterns.append({
                "id": definition["id"],
                "label": definition["label"],
                "reel_count": len(evidence),
                "ratio": round(len(evidence) / max(1, len(selected)), 2),
                "matched_signals": sorted(all_matches),
                "why_it_matters": definition["why"],
                "evidence": evidence,
            })
    return sorted(
        patterns,
        key=lambda row: (row["ratio"], row["reel_count"], PATTERN_SPECIFICITY.get(row["id"], 1), len(row["matched_signals"])),
        reverse=True,
    )


def _storyboard_plan(patterns: list[dict], focus: str) -> tuple[str, list[dict]]:
    definitions = {item["id"]: item for item in PATTERN_DEFINITIONS}
    selected = patterns[:3]
    if not selected:
        hook = f"{focus}, 첫 장면에서 핵심을 보여주세요"
        fallback = (
            ("hero", f"{focus}의 대표 결과를 먼저 보여주기", "정면 또는 탑뷰", hook, "상단"),
            ("close", f"{focus}의 핵심 디테일을 가까이 보여주기", "클로즈업", "가장 먼저 볼 디테일", "하단"),
            ("hand", f"{focus}을 준비하거나 사용하는 동작 담기", "손 팔로잉샷", "이 과정에서 차이가 생깁니다", "상단"),
            ("space", f"{focus}이 놓인 실제 공간과 맥락 보여주기", "와이드 정면샷", "실제로 보면 이런 모습입니다", "하단"),
        )
        target_times = ("0-2초", "2-5초", "5-9초", "9-13초")
        plan = [{
            "time": target_times[index], "scene": scene, "shot": shot,
            "camera": camera, "subtitle": subtitle, "subtitle_position": position,
            "purpose": "공통 패턴 근거가 부족해 제품 주제를 명확히 제시", "evidence_pattern": "근거 부족",
        } for index, (scene, shot, camera, subtitle, position) in enumerate(fallback)]
        plan.append({
            "time": "13-15초", "scene": "cta", "shot": f"{focus} 대표 장면으로 마무리하기",
            "camera": "고정 정면샷", "subtitle": f"{focus} 관련 정보는 저장해두세요", "subtitle_position": "중앙",
            "purpose": "하나의 행동으로 마무리", "evidence_pattern": "근거 부족",
        })
        return hook, plan
    primary = definitions[selected[0]["id"]]
    hook = primary["hook"].format(focus=focus)
    candidates = []
    for pattern in selected:
        definition = definitions[pattern["id"]]
        for scene, shot, camera, subtitle in definition["shots"]:
            candidates.append({
                "scene": scene, "shot": shot, "camera": camera,
                "subtitle": subtitle.format(focus=focus),
                "subtitle_position": "상단" if scene in {"hero", "close", "hand"} else "하단",
                "purpose": definition["why"], "evidence_pattern": pattern["label"],
                "evidence_count": pattern["reel_count"],
            })
    while len(candidates) < 4:
        pattern = selected[0]
        if len(candidates) == 2:
            candidates.append({
                "scene": "space", "shot": f"{pattern['label']}이 드러나는 주변 맥락 함께 담기",
                "camera": "와이드 정면샷", "subtitle": f"{pattern['label']}이 보이는 실제 장면",
                "subtitle_position": "하단", "purpose": primary["why"],
                "evidence_pattern": pattern["label"], "evidence_count": pattern["reel_count"],
            })
        else:
            candidates.append({
                "scene": "hero", "shot": f"{pattern['label']}의 결과를 대표 장면으로 다시 보여주기",
                "camera": "고정 정면샷", "subtitle": f"{focus}에서 확인할 핵심 결과",
                "subtitle_position": "상단", "purpose": primary["why"],
                "evidence_pattern": pattern["label"], "evidence_count": pattern["reel_count"],
            })
    plan = []
    target_times = ("0-2초", "2-5초", "5-9초", "9-13초")
    for index, candidate in enumerate(candidates[:4]):
        row = {**candidate, "time": target_times[index]}
        if index == 0:
            row["subtitle"] = hook
        plan.append(row)
    cta_label = selected[-1]["label"]
    plan.append({
        "time": "13-15초", "scene": "cta",
        "shot": f"{cta_label}을 다시 확인할 수 있는 대표 장면으로 마무리하기",
        "camera": "고정 정면샷", "subtitle": f"{focus} 관련 정보는 저장해두세요",
        "subtitle_position": "중앙", "purpose": "분석 근거와 연결된 저장 행동 유도",
        "evidence_pattern": cta_label, "evidence_count": selected[-1]["reel_count"],
    })
    return hook, plan


def build_signal_synthesis(items: list[dict], query: str = "") -> dict:
    """Create a transparent brief from evidence already collected in Radar.

    This intentionally reports observed repetitions rather than inventing a claim
    about a competitor's creative strategy.
    """
    selected = [item for item in items if isinstance(item, dict)]
    captions = [str(item.get("caption") or "") for item in selected]
    threshold = max(2, math.ceil(len(selected) * 0.5)) if len(selected) >= 2 else 2
    hashtag_docs = Counter()
    term_docs = Counter()
    for caption in captions:
        hashtag_docs.update(set(tag.lower() for tag in re.findall(r"#[0-9A-Za-z가-힣_]+", caption)))
        term_docs.update(set(_terms(caption)))
    tracks = Counter(str(item.get("track") or "").strip() for item in selected if str(item.get("track") or "").strip())
    views = sorted(int(item.get("views") or 0) for item in selected)
    repeated_terms = [term for term, count in term_docs.most_common(8) if count >= threshold]
    repeated_tags = [tag for tag, count in hashtag_docs.most_common(6) if count >= threshold]
    hook_evidence = [
        {"username": item.get("username", ""), "text": _first_line(item.get("caption", "")), "url": item.get("url", "")}
        for item in selected if _first_line(item.get("caption", ""))
    ][:5]
    median_views = views[len(views) // 2] if views else 0
    patterns = _common_patterns(selected, threshold)
    focus_terms = repeated_terms[:3] or [tag.lstrip("#") for tag in repeated_tags[:3]]
    focus = str(query or "").strip() or ", ".join(focus_terms) or "대표 결과"
    hook, plan = _storyboard_plan(patterns, focus)
    structure = [f"{row['time']}: {row['shot']} · 자막 ‘{row['subtitle']}’" for row in plan]
    return {
        "sample_count": len(selected),
        "accounts": sorted({str(item.get("username") or "") for item in selected if item.get("username")}),
        "source_urls": [str(item.get("url") or "") for item in selected if item.get("url")],
        "median_views": median_views,
        "repeated_terms": repeated_terms,
        "repeated_hashtags": repeated_tags,
        "term_evidence": [
            {"term": term, "reel_count": term_docs[term], "sample_count": len(selected)}
            for term in repeated_terms
        ],
        "common_patterns": patterns,
        "common_track": tracks.most_common(1)[0][0] if tracks and tracks.most_common(1)[0][1] >= threshold else "",
        "hook_evidence": hook_evidence,
        "recommended_hook": hook,
        "storyboard_plan": plan,
        "recommended_structure": structure,
        "confidence": "high" if patterns and len(selected) >= 4 else ("medium" if patterns and len(selected) >= 2 else "insufficient"),
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def build_visual_synthesis(analyses: dict[str, dict], selected_items: list[dict]) -> dict:
    """Aggregate only observed AI visual labels, retaining the source count."""
    selected_ids = {str(item.get("media_id") or item.get("url") or "") for item in selected_items}
    selected_by_id = {
        str(item.get("media_id") or item.get("url") or ""): item
        for item in selected_items
    }
    rows = [
        {**value, "_signal": selected_by_id.get(key, {}), "_identity": key}
        for key, value in analyses.items()
        if key in selected_ids and isinstance(value, dict)
    ]
    # Count a visual label at most once per reel. A label is called common only
    # when it appears in at least two and at least half of analyzed reels.
    cameras = Counter(camera for row in rows for camera in set(row.get("camera_angles") or []))
    subtitles = Counter(str(row.get("subtitle_position") or "") for row in rows if row.get("subtitle_position"))
    cut_speeds = Counter(str(row.get("cut_speed") or "") for row in rows if row.get("cut_speed"))
    moods = Counter(str(row.get("bgm_mood") or "") for row in rows if row.get("bgm_mood"))
    threshold = max(2, math.ceil(len(rows) * 0.5)) if len(rows) >= 2 else 2

    def common_bbox(name: str, tolerance: float, source_rows: list[dict] | None = None, required: int | None = None) -> tuple[dict | None, int]:
        active_rows = rows if source_rows is None else source_rows
        minimum = threshold if required is None else required
        boxes = [row.get(name) for row in active_rows if isinstance(row.get(name), dict)]
        if len(boxes) < minimum:
            return None, 0
        keys = ("x", "y", "width", "height")
        try:
            clusters = []
            for anchor in boxes:
                anchor_center = (
                    float(anchor["x"]) + float(anchor["width"]) / 2,
                    float(anchor["y"]) + float(anchor["height"]) / 2,
                )
                cluster = []
                for box in boxes:
                    center = (
                        float(box["x"]) + float(box["width"]) / 2,
                        float(box["y"]) + float(box["height"]) / 2,
                    )
                    if (
                        abs(center[0] - anchor_center[0]) <= tolerance
                        and abs(center[1] - anchor_center[1]) <= tolerance
                        and abs(float(box["width"]) - float(anchor["width"])) <= tolerance * 1.5
                        and abs(float(box["height"]) - float(anchor["height"])) <= tolerance * 1.5
                    ):
                        cluster.append(box)
                clusters.append(cluster)
            common = max(clusters, key=len, default=[])
            if len(common) < minimum:
                return None, 0
            return ({key: round(median(float(box[key]) for box in common), 1) for key in keys}, len(common))
        except (KeyError, TypeError, ValueError):
            return None, 0

    subject_bbox, subject_bbox_count = common_bbox("subject_bbox", tolerance=20)
    subtitle_bbox, subtitle_bbox_count = common_bbox("subtitle_bbox", tolerance=12)

    def observed_median_bbox(name: str, source_rows: list[dict] | None = None, required: int | None = None) -> tuple[dict | None, int]:
        active_rows = rows if source_rows is None else source_rows
        minimum = threshold if required is None else required
        boxes = [row.get(name) for row in active_rows if isinstance(row.get(name), dict)]
        if len(boxes) < minimum:
            return None, 0
        keys = ("x", "y", "width", "height")
        try:
            return ({key: round(median(float(box[key]) for box in boxes), 1) for key in keys}, len(boxes))
        except (KeyError, TypeError, ValueError):
            return None, 0

    subject_bbox_basis = "repeated_cluster" if subject_bbox else ""
    subtitle_bbox_basis = "repeated_cluster" if subtitle_bbox else ""
    if subject_bbox is None:
        subject_bbox, subject_bbox_count = observed_median_bbox("subject_bbox")
        subject_bbox_basis = "observed_median" if subject_bbox else ""
    if subtitle_bbox is None:
        subtitle_bbox, subtitle_bbox_count = observed_median_bbox("subtitle_bbox")
        subtitle_bbox_basis = "observed_median" if subtitle_bbox else ""

    sequence_geometry = []
    normalized_ranges = ((0, 13), (13, 33), (33, 60), (60, 87), (87, 100))
    for index, normalized_range in enumerate(normalized_ranges):
        segment_rows = []
        evidence_times = []
        for row in rows:
            sequence = row.get("composition_sequence") or []
            segment = next(
                (item for item in sequence if isinstance(item, dict) and int(item.get("segment_index", -1)) == index),
                None,
            )
            if segment:
                segment_rows.append(segment)
                evidence_times.append({
                    "timestamp_seconds": float(segment.get("timestamp_seconds") or 0),
                    "duration_seconds": float(row.get("duration_seconds") or 0),
                })
        segment_required = max(2, math.ceil(len(rows) * 0.5)) if len(rows) >= 2 else 2
        segment_subject, segment_subject_count = common_bbox("subject_bbox", 20, segment_rows, segment_required)
        subject_basis = "repeated_cluster" if segment_subject else ""
        if segment_subject is None:
            segment_subject, segment_subject_count = observed_median_bbox("subject_bbox", segment_rows, segment_required)
            subject_basis = "observed_median" if segment_subject else ""
        segment_subtitle, segment_subtitle_count = common_bbox("subtitle_bbox", 12, segment_rows, segment_required)
        subtitle_basis = "repeated_cluster" if segment_subtitle else ""
        if segment_subtitle is None:
            segment_subtitle, segment_subtitle_count = observed_median_bbox("subtitle_bbox", segment_rows, segment_required)
            subtitle_basis = "observed_median" if segment_subtitle else ""
        segment_cameras = Counter(str(item.get("camera") or "") for item in segment_rows if item.get("camera"))
        sequence_geometry.append({
            "segment_index": index,
            "normalized_start": normalized_range[0],
            "normalized_end": normalized_range[1],
            "subject_bbox": segment_subject,
            "subject_bbox_count": segment_subject_count,
            "subject_bbox_basis": subject_basis,
            "subtitle_bbox": segment_subtitle,
            "subtitle_bbox_count": segment_subtitle_count,
            "subtitle_bbox_basis": subtitle_basis,
            "camera": segment_cameras.most_common(1)[0][0] if segment_cameras and segment_cameras.most_common(1)[0][1] >= segment_required else "",
            "evidence_times": evidence_times,
        })

    def valid_box(value: object) -> bool:
        if not isinstance(value, dict):
            return False
        try:
            return float(value["width"]) > 0 and float(value["height"]) > 0
        except (KeyError, TypeError, ValueError):
            return False

    def classify_motion(start: dict, end: dict) -> tuple[str, float]:
        start_area = float(start["width"]) * float(start["height"])
        end_area = float(end["width"]) * float(end["height"])
        scale = math.sqrt(end_area / max(start_area, 1.0))
        start_center = (float(start["x"]) + float(start["width"]) / 2, float(start["y"]) + float(start["height"]) / 2)
        end_center = (float(end["x"]) + float(end["width"]) / 2, float(end["y"]) + float(end["height"]) / 2)
        center_shift = math.dist(start_center, end_center)
        if scale >= 1.12:
            return "zoom_in", round(scale, 2)
        if scale <= 0.89:
            return "zoom_out", round(scale, 2)
        if center_shift >= 8:
            return "pan", round(scale, 2)
        return "hold", round(scale, 2)

    def performance_key(row: dict) -> tuple[float, float, float]:
        signal = row.get("_signal") or {}

        def number(*names: str) -> float:
            for name in names:
                try:
                    if signal.get(name) is not None:
                        return float(signal[name])
                except (TypeError, ValueError):
                    continue
            return 0.0

        return (
            number("rank_score", "total_score", "총점"),
            number("ig_play_count", "views", "view_count", "조회수"),
            number("like_count", "likes", "좋아요"),
        )

    def median_candidate_box(candidates: list[dict], name: str) -> dict | None:
        boxes = [candidate[name] for candidate in candidates if valid_box(candidate.get(name))]
        if not boxes:
            return None
        return {
            key: round(median(float(box[key]) for box in boxes), 1)
            for key in ("x", "y", "width", "height")
        }

    sequence_motion = []
    for index in range(4):
        candidates = []
        for row in rows:
            sequence = row.get("composition_sequence") or []
            start_segment = next((item for item in sequence if isinstance(item, dict) and int(item.get("segment_index", -1)) == index), None)
            end_segment = next((item for item in sequence if isinstance(item, dict) and int(item.get("segment_index", -1)) == index + 1), None)
            start_box = (start_segment or {}).get("subject_bbox")
            end_box = (end_segment or {}).get("subject_bbox")
            if not valid_box(start_box) or not valid_box(end_box):
                continue
            kind, scale = classify_motion(start_box, end_box)
            candidates.append({"kind": kind, "scale": scale, "start_bbox": start_box, "end_bbox": end_box, "row": row})

        required = max(2, math.ceil(len(candidates) * 0.5)) if len(candidates) >= 2 else 2
        counts = Counter(candidate["kind"] for candidate in candidates)
        repeated = [kind for kind, count in counts.most_common() if count >= required and kind in {"zoom_in", "zoom_out", "pan"}]
        basis = "common" if repeated else ""
        chosen_kind = repeated[0] if repeated else "hold"
        supporters = [candidate for candidate in candidates if candidate["kind"] == chosen_kind]
        if not repeated and candidates:
            top_candidate = max(candidates, key=lambda candidate: performance_key(candidate["row"]))
            chosen_kind = top_candidate["kind"]
            supporters = [top_candidate]
            basis = "top_reel" if chosen_kind != "hold" else "stable"

        top_supporter = max(supporters, key=lambda candidate: performance_key(candidate["row"])) if supporters else None
        source_signal = ((top_supporter or {}).get("row") or {}).get("_signal") or {}
        sequence_motion.append({
            "segment_index": index,
            "motion_type": chosen_kind,
            "motion_basis": basis,
            "evidence_count": len(supporters),
            "candidate_count": len(candidates),
            "start_bbox": median_candidate_box(supporters, "start_bbox"),
            "end_bbox": median_candidate_box(supporters, "end_bbox"),
            "scale_ratio": round(median(candidate["scale"] for candidate in supporters), 2) if supporters else 1.0,
            "source_label": str(source_signal.get("username") or source_signal.get("code") or ""),
        })

    final_box = sequence_geometry[-1].get("subject_bbox") if sequence_geometry else None
    sequence_motion.append({
        "segment_index": 4,
        "motion_type": "hold",
        "motion_basis": "stable",
        "evidence_count": int((sequence_geometry[-1] if sequence_geometry else {}).get("subject_bbox_count") or 0),
        "candidate_count": len(rows),
        "start_bbox": final_box,
        "end_bbox": final_box,
        "scale_ratio": 1.0,
        "source_label": "",
    })

    def common_value(counter: Counter) -> str:
        if not counter:
            return ""
        value, count = counter.most_common(1)[0]
        return value if count >= threshold else ""

    return {
        "analyzed_count": len(rows),
        "common_threshold": threshold,
        "top_camera": common_value(cameras),
        "top_subtitle_position": common_value(subtitles),
        "top_cut_speed": common_value(cut_speeds),
        "top_bgm_mood": common_value(moods),
        "subject_bbox": subject_bbox,
        "subtitle_bbox": subtitle_bbox,
        "subject_bbox_count": subject_bbox_count,
        "subtitle_bbox_count": subtitle_bbox_count,
        "subject_bbox_basis": subject_bbox_basis,
        "subtitle_bbox_basis": subtitle_bbox_basis,
        "sequence_geometry": sequence_geometry,
        "sequence_motion": sequence_motion,
        "sequence_analyzed_count": sum(bool(row.get("composition_sequence")) for row in rows),
        "camera_distribution": dict(cameras),
        "subtitle_distribution": dict(subtitles),
        "confidence": "medium" if len(rows) >= 4 else ("low" if len(rows) >= 2 else "insufficient"),
    }
