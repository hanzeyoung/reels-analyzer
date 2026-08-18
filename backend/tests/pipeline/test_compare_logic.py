from datetime import UTC, datetime

from app.pipeline.compare import (
    MIN_GROUP_N,
    build_comparison_result,
    compute_feature_findings,
    compute_timing_stats,
)
from app.schemas.analyze import ReelAnalysis, ShotSegment

NOW = datetime(2026, 8, 14, tzinfo=UTC)


def _shot(angle: str = "정면샷", purpose: str = "정보", movement: str = "고정") -> ShotSegment:
    return ShotSegment(
        index=0,
        t_start=0.0,
        t_end=1.0,
        angle=angle,
        subject="테스트 피사체",
        on_screen_text=None,
        movement=movement,
        purpose=purpose,
        technique=None,
        difficulty="하",
        requires=[],
        solo_alternative=None,
    )


def _reel_analysis(
    code: str,
    *,
    angle: str = "정면샷",
    purpose: str = "정보",
    subtitle_position: str = "없음",
    color_tone: str = "밝음",
    cut_count: int = 3,
    avg_shot_sec: float = 2.0,
    first_shot_sec: float = 1.5,
) -> ReelAnalysis:
    return ReelAnalysis(
        reel_code=code,
        track="breakout",
        bucket="B2",
        shots=[_shot(angle=angle, purpose=purpose)],
        caption_hooks=[],
        color_tone=color_tone,
        subtitle_position=subtitle_position,
        summary="테스트 요약",
        cut_count=cut_count,
        avg_shot_sec=avg_shot_sec,
        first_shot_sec=first_shot_sec,
        audio_title=None,
        model="test-model",
        analyzed_at=NOW,
    )


def test_build_comparison_result_insufficient_when_below_min_n():
    high = [_reel_analysis(f"h{i}") for i in range(MIN_GROUP_N - 1)]
    low = [_reel_analysis(f"l{i}") for i in range(MIN_GROUP_N)]

    result = build_comparison_result(high, low)

    assert result.sufficient is False
    assert result.findings == []
    assert result.timing is None
    assert result.insufficient_reason is not None
    assert result.high_n == MIN_GROUP_N - 1
    assert result.low_n == MIN_GROUP_N


def test_build_comparison_result_sufficient_when_both_at_least_min_n():
    high = [_reel_analysis(f"h{i}") for i in range(MIN_GROUP_N)]
    low = [_reel_analysis(f"l{i}") for i in range(MIN_GROUP_N)]

    result = build_comparison_result(high, low)

    assert result.sufficient is True
    assert result.insufficient_reason is None
    assert result.timing is not None


def test_compute_feature_findings_includes_gap_over_30pp():
    # high: 15개 중 12개가 "탑뷰"(80%), low: 15개 중 1개(6.7%) → gap ≈ 73.3pp
    high = [_reel_analysis(f"h{i}", angle="탑뷰" if i < 12 else "정면샷") for i in range(15)]
    low = [_reel_analysis(f"l{i}", angle="탑뷰" if i < 1 else "정면샷") for i in range(15)]

    findings = compute_feature_findings(high, low)

    angle_findings = [f for f in findings if f.feature == "구도(angle)" and f.high.value == "탑뷰"]
    assert len(angle_findings) == 1
    finding = angle_findings[0]
    assert finding.high.count == 12
    assert finding.high.total == 15
    assert finding.low.count == 1
    assert finding.gap_pp >= 30


def test_compute_feature_findings_excludes_gap_under_30pp():
    # high 8/15(53.3%) vs low 6/15(40%) → gap ≈ 13.3pp, 임계값 미달
    high = [_reel_analysis(f"h{i}", angle="탑뷰" if i < 8 else "정면샷") for i in range(15)]
    low = [_reel_analysis(f"l{i}", angle="탑뷰" if i < 6 else "정면샷") for i in range(15)]

    findings = compute_feature_findings(high, low)

    assert all(not (f.feature == "구도(angle)" and f.high.value == "탑뷰") for f in findings)


def test_compute_feature_findings_empty_group_produces_no_findings():
    assert compute_feature_findings([], [_reel_analysis("l0")]) == []
    assert compute_feature_findings([_reel_analysis("h0")], []) == []


def test_compute_timing_stats_averages_each_group():
    high = [
        _reel_analysis("h0", cut_count=3, avg_shot_sec=2.0, first_shot_sec=1.0),
        _reel_analysis("h1", cut_count=5, avg_shot_sec=4.0, first_shot_sec=3.0),
    ]
    low = [_reel_analysis("l0", cut_count=4, avg_shot_sec=1.0, first_shot_sec=0.5)]

    timing = compute_timing_stats(high, low)

    assert timing.cut_count_high == 4  # (3+5)/2
    assert timing.avg_shot_sec_high == 3.0  # (2+4)/2
    assert timing.first_shot_sec_high == 2.0  # (1+3)/2
    assert timing.cut_count_low == 4
    assert timing.avg_shot_sec_low == 1.0
    assert timing.first_shot_sec_low == 0.5
