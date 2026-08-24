from datetime import UTC, date, datetime

from app.pipeline.guide import (
    _my_reel_block_text,
    _week_of,
    compute_confidence,
    filter_reference_shots,
    render_user_prompt,
)
from app.schemas.analyze import ReelAnalysis, ShotSegment
from app.schemas.compare import ComparisonResult, DifferenceFinding, FeatureCount, TimingStats
from app.schemas.requests import UserConstraints

NOW = datetime(2026, 8, 14, tzinfo=UTC)


def _shot(**overrides) -> ShotSegment:
    defaults = dict(
        index=0, t_start=0.0, t_end=1.0, angle="정면샷", subject="컵에 우유 붓는 손",
        on_screen_text=None, movement="고정", purpose="정보", technique=None,
        difficulty="하", requires=[], solo_alternative=None,
    )
    defaults.update(overrides)
    return ShotSegment(**defaults)


def _reel_analysis(code: str, shots: list[ShotSegment], **overrides) -> ReelAnalysis:
    defaults = dict(
        reel_code=code, track="breakout", bucket="B2", shots=shots, caption_hooks=[],
        color_tone="밝음", subtitle_position="없음", summary="요약", cut_count=len(shots),
        avg_shot_sec=2.0, first_shot_sec=1.5, audio_title=None, model="test-model",
        analyzed_at=NOW,
    )
    defaults.update(overrides)
    return ReelAnalysis(**defaults)


def _sufficient_comparison() -> ComparisonResult:
    return ComparisonResult(
        bucket="B2", high_n=18, low_n=16, sufficient=True,
        findings=[
            DifferenceFinding(
                feature="구도(angle)",
                high=FeatureCount(value="탑뷰", count=14, total=18),
                low=FeatureCount(value="탑뷰", count=2, total=16),
                gap_pp=65.0,
            ),
            DifferenceFinding(
                feature="카메라 움직임(movement)",
                high=FeatureCount(value="고정", count=16, total=18),
                low=FeatureCount(value="고정", count=4, total=16),
                gap_pp=64.0,
            ),
        ],
        timing=TimingStats(
            first_shot_sec_high=1.5, first_shot_sec_low=4.0,
            avg_shot_sec_high=2.0, avg_shot_sec_low=3.5,
            cut_count_high=8.0, cut_count_low=5.0,
        ),
        insufficient_reason=None,
    )


def _insufficient_comparison() -> ComparisonResult:
    return ComparisonResult(
        bucket="B2", high_n=5, low_n=3, sufficient=False, findings=[], timing=None,
        insufficient_reason="표본 부족: 돌파형 5개, 대조군 3개 (각각 최소 15개 필요)",
    )


# ── compute_confidence ──────────────────────────────────────────────


def test_compute_confidence_sufficient_with_two_plus_findings():
    comparison = _sufficient_comparison()
    assert compute_confidence(comparison) == "충분"


def test_compute_confidence_limited_with_one_finding():
    base = _sufficient_comparison()
    comparison = base.model_copy(update={"findings": base.findings[:1]})
    assert compute_confidence(comparison) == "제한적"


def test_compute_confidence_insufficient_when_not_sufficient():
    assert compute_confidence(_insufficient_comparison()) == "불충분"


# ── filter_reference_shots ──────────────────────────────────────────


def test_filter_reference_shots_substitutes_solo_alternative():
    shots = [_shot(requires=["촬영자 1명"], solo_alternative="삼각대로 고정 촬영")]
    constraints = UserConstraints(shooting_alone=True)

    result = filter_reference_shots(shots, constraints)

    assert len(result) == 1
    assert result[0].technique == "삼각대로 고정 촬영"
    assert result[0].requires == []


def test_filter_reference_shots_excludes_when_no_solo_alternative():
    shots = [_shot(requires=["촬영자 1명"], solo_alternative=None)]
    result = filter_reference_shots(shots, UserConstraints(shooting_alone=True))
    assert result == []


def test_filter_reference_shots_excludes_face_subject_when_face_not_allowed():
    shots = [_shot(subject="사장님 얼굴 클로즈업")]
    result = filter_reference_shots(shots, UserConstraints(can_show_face=False))
    assert result == []


def test_filter_reference_shots_keeps_face_subject_when_face_allowed():
    shots = [_shot(subject="사장님 얼굴 클로즈업")]
    result = filter_reference_shots(shots, UserConstraints(can_show_face=True))
    assert len(result) == 1


def test_filter_reference_shots_excludes_missing_equipment():
    shots = [_shot(requires=["짐벌"])]
    result = filter_reference_shots(shots, UserConstraints(equipment=["스마트폰"]))
    assert result == []


def test_filter_reference_shots_keeps_when_equipment_available():
    shots = [_shot(requires=["삼각대"])]
    result = filter_reference_shots(shots, UserConstraints(equipment=["스마트폰", "삼각대"]))
    assert len(result) == 1


# ── render_user_prompt ───────────────────────────────────────────────


def test_render_user_prompt_strips_arrow_comments_and_my_reel_placeholder():
    prompt = render_user_prompt(
        business_type="카페",
        keyword="성수동카페",
        comparison=_sufficient_comparison(),
        breakout=[_reel_analysis("h0", [_shot()])],
        big_account=[_reel_analysis("b0", [_shot()], track="big_account", audio_title="곡A")],
        constraints=UserConstraints(),
        confidence="충분",
    )

    assert "←" not in prompt
    assert "{my_reel_block}" not in prompt
    assert "카페" in prompt
    assert "성수동카페" in prompt
    assert "곡A" in prompt


def test_render_user_prompt_includes_my_reel_diagnosis_block_when_present():
    my_reel = _reel_analysis(
        "MY1", [_shot()], track="my_reel", bucket="unknown",
        cut_count=1, avg_shot_sec=2.0, first_shot_sec=1.5,
    )
    prompt = render_user_prompt(
        business_type="카페", keyword="성수동카페", comparison=_sufficient_comparison(),
        breakout=[_reel_analysis("h0", [_shot()])],
        big_account=[_reel_analysis("b0", [_shot()], track="big_account")],
        constraints=UserConstraints(), confidence="충분", my_reel=my_reel,
    )
    assert "내 릴스 진단" in prompt
    assert "{my_reel_block}" not in prompt
    assert "←" not in prompt


def test_render_user_prompt_insufficient_shows_reason_in_evidence_note():
    prompt = render_user_prompt(
        business_type="카페", keyword="성수동카페", comparison=_insufficient_comparison(),
        breakout=[], big_account=[], constraints=UserConstraints(), confidence="불충분",
    )
    assert "표본 부족" in prompt
    assert "데이터 없음" in prompt  # breakout_shots/timing 등


# ── _my_reel_block_text (P5) ────────────────────────────────────────


def test_my_reel_block_text_none_when_no_my_reel():
    assert _my_reel_block_text(None, _sufficient_comparison()) is None


def test_my_reel_block_text_includes_benchmark_when_timing_present():
    my_reel = _reel_analysis(
        "MY1", [_shot(), _shot(index=1, t_start=1.0, t_end=3.0)],
        track="my_reel", bucket="unknown", cut_count=2, avg_shot_sec=2.5, first_shot_sec=1.0,
    )
    text = _my_reel_block_text(my_reel, _sufficient_comparison())
    assert text is not None
    assert "내 릴스: 컷 수 2개" in text
    assert "벤치마크" in text
    assert "표본 부족" not in text


def test_my_reel_block_text_shows_no_benchmark_when_timing_missing():
    my_reel = _reel_analysis(
        "MY1", [_shot()], track="my_reel", bucket="unknown",
        cut_count=1, avg_shot_sec=2.0, first_shot_sec=1.5,
    )
    text = _my_reel_block_text(my_reel, _insufficient_comparison())
    assert text is not None
    assert "벤치마크 없음(표본 부족)" in text


# ── _week_of ─────────────────────────────────────────────────────────


def test_week_of_returns_monday_of_the_week():
    # 2026-08-14는 금요일 → 그 주 월요일은 2026-08-10
    assert _week_of(date(2026, 8, 14)) == date(2026, 8, 10)
    # 이미 월요일이면 그대로
    assert _week_of(date(2026, 8, 10)) == date(2026, 8, 10)
