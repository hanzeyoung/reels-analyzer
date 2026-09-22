"""Explainable per-store pattern learning from analyzed reels with measured outcomes."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median

from app.core.performance_insights import performance_score


def _split_values(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip() and item.strip() != "-"]


def _parse_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
    except ValueError:
        return None


def _recency_weight(value) -> float:
    published = _parse_datetime(value)
    if not published:
        return 1.0
    age_days = max(0.0, (datetime.now(timezone.utc) - published).total_seconds() / 86400)
    return round(max(0.35, math.exp(-age_days / 120)), 4)


def _hook_style(text: str) -> str:
    text = str(text or "")
    if any(token in text for token in ["?", "왜", "아세요", "궁금"]):
        return "질문형"
    if any(token in text for token in ["전후", "비교", "바뀐", "달라"]):
        return "전후 비교형"
    if any(token in text for token in ["저장", "놓치", "필수", "꼭"]):
        return "행동 유도형"
    if any(char.isdigit() for char in text):
        return "숫자·목록형"
    if text:
        return "결과 선공개형"
    return "후킹 정보 없음"


def _duration_bucket(value: float) -> str:
    if value <= 15:
        return "15초 이하"
    if value <= 30:
        return "16~30초"
    if value <= 45:
        return "31~45초"
    return "46초 이상"


def _measured_score(item: dict) -> float:
    insights = item.get("insights") or {}
    if insights and any(float(insights.get(key) or 0) > 0 for key in ["views", "reach", "saved", "shares"]):
        return performance_score(insights)
    return float(item.get("총점") or item.get("actual_score") or 0)


def _features(item: dict) -> list[tuple[str, str]]:
    analysis = item.get("analysis") or {}
    values = []
    for camera in _split_values(analysis.get("camera_angles") or item.get("촬영구도")):
        values.append(("camera", camera))
    for field, key in [
        ("cut_speed", "cut_speed"),
        ("subtitle_position", "subtitle_position"),
        ("bgm_mood", "bgm_mood"),
    ]:
        value = str(analysis.get(key) or item.get(key) or "").strip()
        if value and value != "-":
            values.append((field, value))
    hook = analysis.get("hook_text") or item.get("후킹") or ""
    values.append(("hook_style", _hook_style(hook)))
    duration = float(item.get("길이(초)") or item.get("duration_seconds") or analysis.get("duration_seconds") or 0)
    if duration:
        values.append(("duration", _duration_bucket(duration)))
    published = _parse_datetime(item.get("업로드") or item.get("published_at"))
    if published:
        values.append(("posting_window", f"{published.weekday()}요일 {published.hour:02d}시"))
    return values


def learn_creator_patterns(reels: list[dict], store_id: str | None = None) -> dict:
    """Estimate feature lift relative to the store's own baseline with recency weighting."""
    eligible = []
    excluded = {"no_measured_result": 0, "no_analysis": 0, "other_store": 0}
    for item in reels:
        if store_id and item.get("store_id") != store_id:
            excluded["other_store"] += 1
            continue
        if float(item.get("조회수") or item.get("views") or (item.get("insights") or {}).get("views") or 0) <= 0:
            excluded["no_measured_result"] += 1
            continue
        if not item.get("analysis"):
            excluded["no_analysis"] += 1
            continue
        eligible.append(item)

    if not eligible:
        return {
            "sample_count": 0, "status": "learning", "confidence": "insufficient",
            "message": "분석과 Meta 실측이 모두 연결된 릴스가 필요합니다.",
            "patterns": [], "top_cameras": [], "top_hooks": [], "recommended_length": None,
            "excluded": excluded,
        }

    scores = [_measured_score(item) for item in eligible]
    baseline = max(median(scores), 1.0)
    feature_stats = defaultdict(lambda: {"weight": 0.0, "weighted_ratio": 0.0, "count": 0})
    winners = []
    for item, score in zip(eligible, scores):
        weight = _recency_weight(item.get("업로드") or item.get("published_at"))
        ratio = max(0.25, min(score / baseline, 3.0))
        if score >= baseline:
            winners.append(item)
        for feature_type, value in _features(item):
            stat = feature_stats[(feature_type, value)]
            stat["weight"] += weight
            stat["weighted_ratio"] += ratio * weight
            stat["count"] += 1

    patterns = []
    for (feature_type, value), stat in feature_stats.items():
        if stat["count"] < 2:
            continue
        average_ratio = stat["weighted_ratio"] / max(stat["weight"], 0.001)
        confidence = "high" if stat["count"] >= 5 else ("medium" if stat["count"] >= 3 else "low")
        patterns.append({
            "feature": feature_type,
            "value": value,
            "count": stat["count"],
            "lift_percent": round((average_ratio - 1) * 100, 1),
            "confidence": confidence,
        })
    patterns.sort(key=lambda item: (item["lift_percent"], item["count"]), reverse=True)

    winner_lengths = [
        float(item.get("길이(초)") or item.get("duration_seconds") or (item.get("analysis") or {}).get("duration_seconds") or 0)
        for item in winners
    ]
    winner_lengths = [value for value in winner_lengths if value > 0]
    status = "ready" if len(eligible) >= 8 else ("provisional" if len(eligible) >= 3 else "learning")
    confidence = "high" if len(eligible) >= 15 else ("medium" if len(eligible) >= 8 else ("low" if len(eligible) >= 3 else "insufficient"))

    def top_values(feature: str, limit: int = 3) -> list[str]:
        return [item["value"] for item in patterns if item["feature"] == feature and item["lift_percent"] > 0][:limit]

    return {
        "sample_count": len(eligible),
        "winner_count": len(winners),
        "baseline_score": round(baseline, 1),
        "status": status,
        "confidence": confidence,
        "message": {
            "ready": "내 매장의 실측 성과 대비 상승 패턴을 추천에 반영합니다.",
            "provisional": "초기 패턴입니다. 표본이 8개 이상 쌓이면 추천 안정성이 높아집니다.",
            "learning": f"현재 유효 표본은 {len(eligible)}개입니다. 분석+실측 영상 3개부터 초기 패턴을 표시합니다.",
        }[status],
        "patterns": patterns[:12],
        "top_cameras": top_values("camera"),
        "top_hooks": top_values("hook_style"),
        "top_cut_speeds": top_values("cut_speed"),
        "top_subtitle_positions": top_values("subtitle_position"),
        "top_bgm_moods": top_values("bgm_mood"),
        "best_posting_windows": top_values("posting_window"),
        "recommended_length": round(median(winner_lengths)) if winner_lengths else None,
        "excluded": excluded,
    }


def personalize_with_memory(guide: dict, memory: dict) -> dict:
    """Apply only positive, repeatable store patterns and retain confidence metadata."""
    result = dict(guide)
    result["creator_memory"] = memory
    if memory.get("status") not in {"provisional", "ready"}:
        return result
    if memory.get("top_cameras"):
        result["camera"] = memory["top_cameras"][0]
        result["camera_reason"] = f"내 매장 실측 성과 기준 상승 패턴입니다. 신뢰도: {memory.get('confidence', 'low')}."
    if memory.get("recommended_length"):
        result["recommended_length"] = f"{memory['recommended_length']}초 안팎"
    if memory.get("top_hooks"):
        result["memory_hook_style"] = memory["top_hooks"][0]
        result["hooks"] = [f"[{memory['top_hooks'][0]}] {hook}" for hook in result.get("hooks", [])]
    return result
