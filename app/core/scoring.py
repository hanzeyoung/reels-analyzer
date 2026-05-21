"""
core/scoring.py
성과 스코어링 알고리즘
공식: (조회수 × 0.2) + (좋아요 × 0.3) + (저장/공유 × 0.5)
"""

from dataclasses import dataclass
from typing import Optional
import math


# ── 가중치 설정 ────────────────────────────────
WEIGHT_VIEW = 0.2
WEIGHT_LIKE = 0.3
WEIGHT_SAVE_SHARE = 0.5

# 등급 기준 (정규화 점수 기준)
TIER_THRESHOLDS = {
    "S": 80,
    "A": 60,
    "B": 40,
    "C": 0,
}


@dataclass
class ReelMetrics:
    """Meta Graph API에서 수집한 릴스 지표"""
    reel_id: str
    view_count: int = 0
    like_count: int = 0
    save_count: int = 0
    share_count: int = 0
    comment_count: int = 0
    duration_seconds: float = 0.0


@dataclass
class ScoreResult:
    """스코어링 결과"""
    reel_id: str
    score_view: float
    score_like: float
    score_save_share: float
    total_score: float
    tier: str
    percentile: Optional[float] = None   # 전체 중 상위 몇 %인지 (나중에 채움)


def normalize(value: int, max_value: int) -> float:
    """
    값을 0~100 사이로 정규화.
    max_value가 0이면 0 반환 (ZeroDivision 방지)
    """
    if max_value == 0:
        return 0.0
    return min(value / max_value * 100, 100.0)


def calculate_score(metrics: ReelMetrics, max_values: dict) -> ScoreResult:
    """
    단일 릴스의 성과 점수를 계산합니다.

    Args:
        metrics: 릴스 지표
        max_values: 비교 기준이 되는 최댓값 dict
                    {"view": int, "like": int, "save_share": int}

    Returns:
        ScoreResult
    """
    # 각 지표 정규화 (0~100)
    norm_view = normalize(metrics.view_count, max_values.get("view", 1))
    norm_like = normalize(metrics.like_count, max_values.get("like", 1))
    norm_save_share = normalize(
        metrics.save_count + metrics.share_count,
        max_values.get("save_share", 1)
    )

    # 가중합 계산
    score_view = norm_view * WEIGHT_VIEW
    score_like = norm_like * WEIGHT_LIKE
    score_save_share = norm_save_share * WEIGHT_SAVE_SHARE
    total = score_view + score_like + score_save_share

    # 등급 산출
    tier = _get_tier(total)

    return ScoreResult(
        reel_id=metrics.reel_id,
        score_view=round(score_view, 2),
        score_like=round(score_like, 2),
        score_save_share=round(score_save_share, 2),
        total_score=round(total, 2),
        tier=tier,
    )


def batch_score(metrics_list: list[ReelMetrics]) -> list[ScoreResult]:
    """
    여러 릴스를 한번에 스코어링합니다.
    max_values를 배치 내 최댓값으로 자동 산출합니다.
    """
    if not metrics_list:
        return []

    # 배치 내 최댓값 산출
    max_view = max(m.view_count for m in metrics_list) or 1
    max_like = max(m.like_count for m in metrics_list) or 1
    max_save_share = max(m.save_count + m.share_count for m in metrics_list) or 1

    max_values = {
        "view": max_view,
        "like": max_like,
        "save_share": max_save_share,
    }

    results = [calculate_score(m, max_values) for m in metrics_list]

    # 퍼센타일 계산 (내림차순 정렬 기준)
    sorted_scores = sorted([r.total_score for r in results], reverse=True)
    for result in results:
        rank = sorted_scores.index(result.total_score) + 1
        result.percentile = round((1 - rank / len(results)) * 100, 1)

    return results


def _get_tier(score: float) -> str:
    """점수를 S/A/B/C 등급으로 변환"""
    for tier, threshold in TIER_THRESHOLDS.items():
        if score >= threshold:
            return tier
    return "C"


# ── 빠른 테스트 ───────────────────────────────
if __name__ == "__main__":
    sample = [
        ReelMetrics("reel_001", view_count=50000, like_count=3000, save_count=800, share_count=200),
        ReelMetrics("reel_002", view_count=120000, like_count=1500, save_count=200, share_count=50),
        ReelMetrics("reel_003", view_count=8000, like_count=900, save_count=1200, share_count=600),
    ]

    results = batch_score(sample)
    for r in results:
        print(f"[{r.tier}] {r.reel_id} | 총점: {r.total_score} | 상위 {r.percentile}%")
