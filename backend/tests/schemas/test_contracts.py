from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.schemas import (
    Account,
    AnalysisRequest,
    AudioRecommendation,
    CaptionDraft,
    ComparisonResult,
    Cut,
    CutList,
    DiagnosisCard,
    DifferenceFinding,
    FeatureCount,
    Guide,
    Job,
    RawReel,
    ReelAnalysis,
    ReelMetrics,
    ReelPool,
    ScoredReel,
    ShotListItem,
    ShotSegment,
    TimingStats,
    UserConstraints,
    VisionAnalysis,
    VisionShotDescription,
)


def test_user_constraints_defaults():
    c = UserConstraints()
    assert c.shooting_alone is True
    assert c.equipment == ["스마트폰"]


def test_user_constraints_rejects_extra_field():
    with pytest.raises(ValidationError):
        UserConstraints(unknown_field=True)


def test_analysis_request_valid():
    req = AnalysisRequest(
        keyword="성수동카페",
        business_type="카페",
        constraints=UserConstraints(),
    )
    assert req.my_reel_url is None


def test_raw_reel_valid():
    reel = RawReel(
        code="Cabc123",
        url="https://instagram.com/reel/Cabc123",
        username="cafe_seongsu",
        taken_at=datetime(2026, 8, 1),
    )
    assert reel.play_count == 0
    assert reel.hashtags == []


def test_raw_reel_rejects_extra_field():
    with pytest.raises(ValidationError):
        RawReel(
            code="Cabc123",
            url="https://x",
            username="a",
            taken_at=datetime(2026, 8, 1),
            save_count=10,
        )


def test_account_follower_count_none_allowed():
    account = Account(username="cafe_seongsu")
    assert account.follower_count is None


def test_reel_metrics_reach_multiple_optional():
    m = ReelMetrics(engagement_rate=0.1, share_rate=0.02, reach_multiple=None)
    assert m.reach_multiple is None


def _sample_raw_reel() -> RawReel:
    return RawReel(
        code="Cabc123",
        url="https://instagram.com/reel/Cabc123",
        username="cafe_seongsu",
        taken_at=datetime(2026, 8, 1),
    )


def test_scored_reel_valid():
    scored = ScoredReel(
        reel=_sample_raw_reel(),
        account=Account(username="cafe_seongsu"),
        metrics=ReelMetrics(engagement_rate=0.1, share_rate=0.02, reach_multiple=None),
        bucket="unknown",
    )
    assert scored.track is None


def test_scored_reel_rejects_reach_multiple_when_follower_unknown():
    # 계약 불변식 2: follower_count is None → reach_multiple도 None이어야 한다
    with pytest.raises(ValidationError):
        ScoredReel(
            reel=_sample_raw_reel(),
            account=Account(username="cafe_seongsu", follower_count=None),
            metrics=ReelMetrics(engagement_rate=0.1, share_rate=0.02, reach_multiple=3.2),
            bucket="unknown",
        )


def test_reel_pool_valid():
    scored = ScoredReel(
        reel=_sample_raw_reel(),
        account=Account(username="cafe_seongsu"),
        metrics=ReelMetrics(engagement_rate=0.1, share_rate=0.02, reach_multiple=None),
        bucket="unknown",
        track="breakout",
    )
    pool = ReelPool(
        keyword="성수동카페",
        business_type="카페",
        collected_count=180,
        after_recency_count=90,
        after_relevance_count=80,
        after_dedup_count=70,
        follower_data_available=False,
        bucket_config_id=None,
        breakout=[scored],
        big_account=[],
        control=[],
    )
    assert pool.after_dedup_count == 70


def test_cut_rejects_invalid_time_order():
    with pytest.raises(ValidationError):
        Cut(index=0, t_start=5.0, t_end=1.0, frame_path="/tmp/f0.jpg")


def test_cut_list_valid():
    cl = CutList(
        reel_code="Cabc123",
        duration_sec=12.0,
        cuts=[Cut(index=0, t_start=0.0, t_end=3.0, frame_path="/tmp/f0.jpg")],
        cut_count=1,
        avg_shot_sec=3.0,
        first_shot_sec=3.0,
    )
    assert cl.source == "ffmpeg_scene_detect"


def _sample_shot_description(index: int = 0) -> VisionShotDescription:
    return VisionShotDescription(
        index=index,
        angle="클로즈업",
        subject="컵에 우유를 붓는 손",
        on_screen_text="이거 모르면 손해",
        movement="고정",
        purpose="후킹",
        technique=None,
        difficulty="하",
        requires=[],
        solo_alternative=None,
    )


def test_vision_analysis_valid():
    va = VisionAnalysis(
        shots=[_sample_shot_description()],
        caption_hooks=["숫자 포함"],
        color_tone="따뜻함",
        subtitle_position="하단",
        summary="요약",
    )
    assert len(va.shots) == 1


def test_shot_segment_rejects_invalid_time_order():
    with pytest.raises(ValidationError):
        ShotSegment(**_sample_shot_description().model_dump(), t_start=3.0, t_end=1.0)


def test_reel_analysis_valid():
    analysis = ReelAnalysis(
        reel_code="Cabc123",
        track="breakout",
        bucket="B1",
        shots=[ShotSegment(**_sample_shot_description().model_dump(), t_start=0.0, t_end=3.0)],
        caption_hooks=["숫자 포함"],
        color_tone="따뜻함",
        subtitle_position="하단",
        summary="요약",
        cut_count=1,
        avg_shot_sec=3.0,
        first_shot_sec=3.0,
        audio_title=None,
        model="claude-sonnet",
        analyzed_at=datetime(2026, 8, 1),
    )
    assert analysis.shots[0].t_start < analysis.shots[0].t_end


def test_reel_analysis_rejects_shots_out_of_order():
    # 계약 불변식 3: shots는 t_start 오름차순이어야 한다
    shot_a = ShotSegment(**_sample_shot_description(0).model_dump(), t_start=5.0, t_end=8.0)
    shot_b = ShotSegment(**_sample_shot_description(1).model_dump(), t_start=0.0, t_end=3.0)
    with pytest.raises(ValidationError):
        ReelAnalysis(
            reel_code="Cabc123",
            track="breakout",
            bucket="B1",
            shots=[shot_a, shot_b],
            caption_hooks=[],
            color_tone="따뜻함",
            subtitle_position="하단",
            summary="요약",
            cut_count=2,
            avg_shot_sec=3.0,
            first_shot_sec=3.0,
            audio_title=None,
            model="claude-sonnet",
            analyzed_at=datetime(2026, 8, 1),
        )


def test_audio_recommendation_rejects_seen_count_over_total():
    with pytest.raises(ValidationError):
        AudioRecommendation(title="lofi beat", seen_count=13, total=12)


def test_feature_count_rejects_count_over_total():
    with pytest.raises(ValidationError):
        FeatureCount(value="탑뷰", count=20, total=18)


def test_comparison_result_insufficient_requires_empty_findings():
    with pytest.raises(ValidationError):
        ComparisonResult(
            bucket="B1",
            high_n=5,
            low_n=5,
            sufficient=False,
            findings=[
                DifferenceFinding(
                    feature="구도",
                    high=FeatureCount(value="탑뷰", count=14, total=18),
                    low=FeatureCount(value="탑뷰", count=4, total=18),
                    gap_pp=55.5,
                )
            ],
            timing=None,
            insufficient_reason=None,
        )


def test_comparison_result_sufficient_valid():
    result = ComparisonResult(
        bucket="B1",
        high_n=18,
        low_n=18,
        sufficient=True,
        findings=[],
        timing=TimingStats(
            first_shot_sec_high=1.8,
            first_shot_sec_low=5.2,
            avg_shot_sec_high=2.1,
            avg_shot_sec_low=3.4,
            cut_count_high=9,
            cut_count_low=6,
        ),
        insufficient_reason=None,
    )
    assert result.sufficient is True


def test_guide_requires_caveat_when_not_confident():
    with pytest.raises(ValidationError):
        Guide(
            business_type="카페",
            keyword="성수동카페",
            week_of=date(2026, 8, 4),
            shot_list=[],
            caption_drafts=[],
            audio=[],
            diagnosis=[],
            evidence_note="최근 30일 기준",
            confidence="불충분",
            caveat=None,
        )


def test_guide_valid_when_confident():
    guide = Guide(
        business_type="카페",
        keyword="성수동카페",
        week_of=date(2026, 8, 4),
        shot_list=[
            ShotListItem(
                order=1,
                t_start_sec=0.0,
                duration_sec=2.0,
                angle="클로즈업",
                subject="커피 붓는 손",
                on_screen_text=None,
                note="폰을 30cm 위에 고정",
            )
        ],
        caption_drafts=[CaptionDraft(text="이거 모르면 손해", pattern="숫자 포함")],
        audio=[AudioRecommendation(title="lofi beat", seen_count=4, total=12)],
        diagnosis=[
            DiagnosisCard(
                metric="첫 컷 길이", mine="5.2초", benchmark="1.8초", gap_note="후킹이 느리다"
            )
        ],
        evidence_note="최근 30일, 팔로워 1천~1만 구간 18개 기준",
        confidence="충분",
        caveat=None,
    )
    assert guide.caveat is None


def test_job_valid():
    job = Job(
        id="00000000-0000-0000-0000-000000000000",
        status="queued",
        created_at=datetime(2026, 8, 1),
        updated_at=datetime(2026, 8, 1),
        request=AnalysisRequest(
            keyword="성수동카페", business_type="카페", constraints=UserConstraints()
        ),
    )
    assert job.stage is None
    assert job.result is None
