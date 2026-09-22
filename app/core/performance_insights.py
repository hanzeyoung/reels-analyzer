"""Normalize account metrics and compare AI predictions with published results."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
from statistics import median
from typing import Any


METRIC_ALIASES = {
    "views": ("views", "plays", "video_views", "ig_reels_video_view_total_time"),
    "reach": ("reach",),
    "likes": ("likes", "like_count"),
    "comments": ("comments", "comments_count", "comment_count"),
    "saved": ("saved", "saves", "save_count"),
    "shares": ("shares", "share_count"),
    "watch_time_ms": ("ig_reels_video_view_total_time", "watch_time_ms"),
    "avg_watch_time_ms": ("ig_reels_avg_watch_time", "avg_watch_time_ms"),
}


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(float(value), high))


def normalize_insights(raw: dict | None) -> dict:
    """Return a stable metric shape across Graph API versions and local rows."""
    raw = raw or {}
    normalized = {}
    for target, aliases in METRIC_ALIASES.items():
        normalized[target] = next(
            (_number(raw[name]) for name in aliases if name in raw and raw[name] is not None),
            0.0,
        )

    views = max(normalized["views"], 1.0)
    reach = max(normalized["reach"], 1.0)
    normalized["engagement_rate"] = round(
        (normalized["likes"] + normalized["comments"] + normalized["saved"] + normalized["shares"])
        / reach
        * 100,
        2,
    )
    normalized["save_rate"] = round(normalized["saved"] / views * 100, 2)
    normalized["share_rate"] = round(normalized["shares"] / views * 100, 2)
    normalized["avg_watch_seconds"] = round(normalized["avg_watch_time_ms"] / 1000, 2)
    normalized["source"] = "measured"
    return normalized


def performance_score(metrics: dict) -> float:
    """Score published performance without letting raw reach dominate the result."""
    normalized = normalize_insights(metrics)
    score = (
        min(normalized["engagement_rate"] / 12, 1) * 35
        + min(normalized["save_rate"] / 4, 1) * 30
        + min(normalized["share_rate"] / 2, 1) * 20
        + min(normalized["avg_watch_seconds"] / 12, 1) * 15
    )
    return round(score, 1)


def build_prediction_calibration(reels: list[dict]) -> dict:
    """Estimate store-specific prediction bias from reels that have both AI and measured outcomes."""
    errors = []
    for item in reels:
        analysis = item.get("analysis") or {}
        predicted = _number(analysis.get("overall_score") or analysis.get("predicted_performance_score"))
        metrics = item.get("insights") or {}
        if predicted > 0 and any(_number(metrics.get(key)) > 0 for key in ["views", "reach", "saved", "shares"]):
            errors.append(performance_score(metrics) - predicted)
    if not errors:
        return {"sample_count": 0, "bias": 0.0, "mae": None, "confidence": "insufficient"}
    bias = float(median(errors))
    residuals = sorted(abs(error - bias) for error in errors)
    mae = sum(residuals) / len(errors)
    interval_index = min(len(residuals) - 1, max(0, round((len(residuals) - 1) * 0.8)))
    interval_80 = residuals[interval_index]
    return {
        "sample_count": len(errors),
        "bias": round(bias, 1),
        "mae": round(mae, 1),
        "error_interval_80": round(interval_80, 1),
        "confidence": "medium" if len(errors) >= 10 else ("low" if len(errors) >= 5 else "insufficient"),
    }


def compare_prediction_to_actual(
    analysis: dict | None,
    metrics: dict | None,
    calibration: dict | None = None,
) -> dict:
    """Compare explicitly labelled AI predictions with measured account metrics."""
    analysis = analysis or {}
    predicted = _number(analysis.get("overall_score") or analysis.get("predicted_performance_score"))
    calibration = calibration or {}
    adjusted_predicted = _clamp(predicted + _number(calibration.get("bias"))) if predicted else 0.0
    interval = _number(calibration.get("error_interval_80"))
    actual = performance_score(metrics or {})
    delta = round(actual - adjusted_predicted, 1) if adjusted_predicted else None

    if delta is None:
        verdict = "AI 예측 점수가 없어 실제 성과만 표시합니다."
    elif delta >= 10:
        verdict = "실제 성과가 예측보다 높았습니다. 잘된 실행 요소를 개인 패턴에 반영합니다."
    elif delta <= -10:
        verdict = "실제 성과가 예측보다 낮았습니다. 게시 맥락과 초반 이탈 지표를 함께 점검하세요."
    else:
        verdict = "AI 예측과 실제 성과가 비슷한 범위였습니다."

    return {
        "raw_predicted_score": round(predicted, 1) if predicted else None,
        "predicted_score": round(adjusted_predicted, 1) if adjusted_predicted else None,
        "predicted_range_80": [
            round(_clamp(adjusted_predicted - interval), 1),
            round(_clamp(adjusted_predicted + interval), 1),
        ] if adjusted_predicted and interval else None,
        "actual_score": actual,
        "delta": delta,
        "verdict": verdict,
        "predicted_label": "AI 예상",
        "actual_label": "Meta 실측",
        "calibration": calibration,
    }


def build_account_baseline(items: list[dict]) -> dict:
    """Build a robust baseline from published reels for relative comparisons."""
    normalized = [normalize_insights(item.get("insights", item)) for item in items]
    if not normalized:
        return {"count": 0, "median_views": 0, "median_engagement_rate": 0, "updated_at": None}
    return {
        "count": len(normalized),
        "median_views": round(median(item["views"] for item in normalized)),
        "median_engagement_rate": round(median(item["engagement_rate"] for item in normalized), 2),
        "median_save_rate": round(median(item["save_rate"] for item in normalized), 2),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def append_performance_snapshot(
    reel_id: str,
    insights: dict,
    permalink: str = "",
    path: str | Path = "user_reels/performance_history.jsonl",
) -> dict:
    """Append immutable measured observations so growth can be compared over time."""
    snapshot = {
        "reel_id": str(reel_id),
        "permalink": permalink,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "insights": normalize_insights(insights),
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as file:
        file.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    return snapshot


def load_performance_history(
    reel_id: str | None = None,
    path: str | Path = "user_reels/performance_history.jsonl",
) -> list[dict]:
    target = Path(path)
    if not target.exists():
        return []
    rows = []
    for line in target.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if reel_id is None or str(item.get("reel_id")) == str(reel_id):
            rows.append(item)
    return sorted(rows, key=lambda item: item.get("captured_at", ""))


def compare_measured_snapshots(history: list[dict]) -> dict | None:
    if len(history) < 2:
        return None
    previous = normalize_insights(history[-2].get("insights"))
    current = normalize_insights(history[-1].get("insights"))
    return {
        "from": history[-2].get("captured_at"),
        "to": history[-1].get("captured_at"),
        "views_delta": int(current["views"] - previous["views"]),
        "reach_delta": int(current["reach"] - previous["reach"]),
        "saved_delta": int(current["saved"] - previous["saved"]),
        "shares_delta": int(current["shares"] - previous["shares"]),
        "engagement_rate_delta": round(current["engagement_rate"] - previous["engagement_rate"], 2),
    }


def compare_snapshot_windows(
    history: list[dict],
    windows_hours: tuple[int, ...] = (24, 72, 168),
) -> dict[str, dict | None]:
    """Compare the latest measured snapshot with observations at fixed lookback windows."""
    if not history:
        return {str(hours): None for hours in windows_hours}

    parsed = []
    for item in history:
        try:
            captured_at = datetime.fromisoformat(str(item.get("captured_at", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if captured_at.tzinfo is not None:
            captured_at = captured_at.replace(tzinfo=None)
        parsed.append((captured_at, item))
    if not parsed:
        return {str(hours): None for hours in windows_hours}

    parsed.sort(key=lambda pair: pair[0])
    current_time, current_item = parsed[-1]
    current = normalize_insights(current_item.get("insights"))
    result: dict[str, dict | None] = {}
    for hours in windows_hours:
        cutoff = current_time - timedelta(hours=hours)
        candidates = [pair for pair in parsed[:-1] if pair[0] <= cutoff]
        if not candidates:
            result[str(hours)] = None
            continue
        baseline_time, baseline_item = candidates[-1]
        baseline = normalize_insights(baseline_item.get("insights"))
        result[str(hours)] = {
            "from": baseline_time.isoformat(timespec="seconds"),
            "to": current_time.isoformat(timespec="seconds"),
            "views_delta": int(current["views"] - baseline["views"]),
            "reach_delta": int(current["reach"] - baseline["reach"]),
            "saved_delta": int(current["saved"] - baseline["saved"]),
            "shares_delta": int(current["shares"] - baseline["shares"]),
        }
    return result
