from datetime import UTC, datetime

from app.pipeline.score import (
    BUCKET_UPPER_BOUNDS,
    build_scored_reel,
    calculate_metrics,
    classify_bucket,
    compute_percentile_boundaries,
    select_big_account,
    select_breakout,
    select_control,
)
from app.schemas.collect import Account, RawReel

NOW = datetime(2026, 8, 6, tzinfo=UTC)


def _reel(**overrides) -> RawReel:
    defaults = dict(
        code="Cabc123",
        url="https://instagram.com/reel/Cabc123",
        username="cafe_seongsu",
        taken_at=NOW,
        play_count=1000,
        like_count=80,
        comment_count=10,
        share_count=10,
    )
    defaults.update(overrides)
    return RawReel(**defaults)


def _account(follower_count: int | None) -> Account:
    return Account(username="cafe_seongsu", follower_count=follower_count)


# ── calculate_metrics ────────────────────────────────────────────────


def test_calculate_metrics_with_follower_count():
    reel = _reel(play_count=1000, like_count=80, comment_count=10, share_count=10)
    metrics = calculate_metrics(reel, _account(2000))

    assert metrics.engagement_rate == 0.1  # (80+10+10)/1000
    assert metrics.share_rate == 0.01  # 10/1000
    assert metrics.reach_multiple == 0.5  # 1000/2000


def test_calculate_metrics_without_follower_count_reach_multiple_is_none():
    reel = _reel(play_count=1000, like_count=80, comment_count=10, share_count=10)
    metrics = calculate_metrics(reel, _account(None))
    assert metrics.reach_multiple is None


def test_calculate_metrics_zero_play_count_does_not_divide_by_zero():
    reel = _reel(play_count=0, like_count=5, comment_count=0, share_count=0)
    metrics = calculate_metrics(reel, _account(1000))
    assert metrics.engagement_rate == 5.0  # 5 / max(0,1)
    assert metrics.reach_multiple == 0.0  # 0 / max(1000,1)


def test_calculate_metrics_like_count_none_excluded_not_zeroed():
    # P6.5(2026-08-24): 좋아요 비공개(None)는 0으로 채우지 않고 분자에서 뺀다.
    reel = _reel(play_count=1000, like_count=None, comment_count=10, share_count=10)
    metrics = calculate_metrics(reel, _account(2000))
    assert metrics.engagement_rate == 0.02  # (0+10+10)/1000, like 기여 없음


# ── classify_bucket ──────────────────────────────────────────────────


def test_classify_bucket_boundaries():
    assert classify_bucket(None) == "unknown"
    assert classify_bucket(0) == "B1"
    assert classify_bucket(999) == "B1"
    assert classify_bucket(1_000) == "B2"
    assert classify_bucket(9_999) == "B2"
    assert classify_bucket(10_000) == "B3"
    assert classify_bucket(99_999) == "B3"
    assert classify_bucket(100_000) == "B4"
    assert classify_bucket(1_000_000) == "B4"


def test_classify_bucket_with_custom_boundaries():
    custom = {"B1": 500, "B2": 5_000, "B3": 50_000}
    assert classify_bucket(400, custom) == "B1"
    assert classify_bucket(4_000, custom) == "B2"
    assert classify_bucket(500, custom) == "B2"  # 커스텀 경계면 999는 더 이상 B1이 아님


def test_build_scored_reel_combines_metrics_and_bucket():
    reel = _reel()
    scored = build_scored_reel(reel, _account(500))
    assert scored.bucket == "B1"
    assert scored.track is None
    assert scored.metrics.reach_multiple is not None


# ── compute_percentile_boundaries ──────────────────────────────────────


def test_compute_percentile_boundaries_splits_into_tertiles():
    # 1~300 균등분포. 33%/66% 컷포인트는 대략 100/200 근처여야 한다.
    follower_counts = list(range(1, 301))
    boundaries = compute_percentile_boundaries(follower_counts)

    assert 90 <= boundaries["B1"] <= 110
    assert 190 <= boundaries["B2"] <= 210
    assert boundaries["B1"] < boundaries["B2"]
    # B3(메가 계정 절대 기준)는 분위수로 안 건드리고 고정값을 유지한다(판단, 계약 3-1).
    assert boundaries["B3"] == BUCKET_UPPER_BOUNDS["B3"]


# ── track selection ──────────────────────────────────────────────────


def _scored(code: str, *, follower_count: int | None, play_count: int, engagement: float):
    # engagement_rate를 원하는 값으로 맞추기 위해 like_count로 역산 (play=1000 고정)
    reel = _reel(
        code=code,
        play_count=play_count,
        like_count=int(engagement * 1000),
        comment_count=0,
        share_count=0,
    )
    return build_scored_reel(reel, _account(follower_count))


def test_select_breakout_picks_top_reach_multiple_within_b1_b2():
    # reach_multiple: small_high=10, mid=1.6, small_low=1.2, big은 B4라 애초에 제외
    small_high = _scored("small_high", follower_count=500, play_count=5000, engagement=0.1)  # B1
    small_low = _scored("small_low", follower_count=500, play_count=600, engagement=0.1)  # B1
    mid = _scored("mid", follower_count=5000, play_count=8000, engagement=0.1)  # B2
    big = _scored("big", follower_count=200_000, play_count=50000, engagement=0.1)  # B4

    result = select_breakout(
        [small_high, small_low, mid, big], top_n=2, follower_data_available=True
    )

    codes = [r.reel.code for r in result]
    assert codes == ["small_high", "mid"]
    assert all(r.track == "breakout" for r in result)


def test_select_breakout_falls_back_to_engagement_rate_when_no_follower_data():
    a = _scored("a", follower_count=None, play_count=1000, engagement=0.3)
    b = _scored("b", follower_count=None, play_count=1000, engagement=0.1)

    result = select_breakout([a, b], top_n=1, follower_data_available=False)

    assert [r.reel.code for r in result] == ["a"]


def test_select_big_account_empty_when_no_follower_data():
    big = _scored("big", follower_count=200_000, play_count=50000, engagement=0.1)
    result = select_big_account([big], top_n=5, follower_data_available=False)
    assert result == []


def test_select_big_account_picks_top_play_count_within_b4():
    big1 = _scored("big1", follower_count=200_000, play_count=50_000, engagement=0.1)
    big2 = _scored("big2", follower_count=200_000, play_count=90_000, engagement=0.1)
    # B1이라 play_count가 아무리 높아도 big_account 후보에서 제외돼야 한다
    small = _scored("small", follower_count=500, play_count=999_999, engagement=0.1)

    result = select_big_account([big1, big2, small], top_n=1, follower_data_available=True)

    assert [r.reel.code for r in result] == ["big2"]
    assert result[0].track == "big_account"


def test_select_control_excludes_breakout_and_picks_lowest_in_same_bucket():
    high = _scored("high", follower_count=500, play_count=9000, engagement=0.1)  # B1
    mid = _scored("mid", follower_count=500, play_count=3000, engagement=0.1)  # B1
    low = _scored("low", follower_count=500, play_count=100, engagement=0.1)  # B1
    other_bucket = _scored("other", follower_count=50_000, play_count=100, engagement=0.1)  # B3

    breakout = select_breakout(
        [high, mid, low, other_bucket], top_n=1, follower_data_available=True
    )
    assert [r.reel.code for r in breakout] == ["high"]

    control = select_control(
        [high, mid, low, other_bucket], breakout, top_n=1, follower_data_available=True
    )

    assert [r.reel.code for r in control] == ["low"]
    assert control[0].track == "control"


def test_select_control_without_follower_data_uses_engagement_rate():
    high_engagement = _scored("high_eng", follower_count=None, play_count=1000, engagement=0.3)
    low_engagement = _scored("low_eng", follower_count=None, play_count=1000, engagement=0.05)

    breakout = select_breakout(
        [high_engagement, low_engagement], top_n=1, follower_data_available=False
    )
    control = select_control(
        [high_engagement, low_engagement], breakout, top_n=1, follower_data_available=False
    )

    assert [r.reel.code for r in control] == ["low_eng"]


def test_select_control_excludes_unknown_like_count_when_no_follower_data():
    # P6.5(2026-08-24): like_count=None인 릴스는 engagement_rate가 실제보다 낮게 나와서
    # control(하위) 후보에 부당하게 쏠릴 수 있다 — engagement_rate 랭킹 분기에서만 제외.
    known_low = _scored("known_low", follower_count=None, play_count=1000, engagement=0.05)
    unknown_like = build_scored_reel(
        _reel(code="unknown_like", play_count=1000, like_count=None, comment_count=0,
              share_count=0),
        _account(None),
    )
    high_engagement = _scored("high_eng", follower_count=None, play_count=1000, engagement=0.3)

    breakout = select_breakout(
        [known_low, unknown_like, high_engagement], top_n=1, follower_data_available=False
    )
    control = select_control(
        [known_low, unknown_like, high_engagement], breakout, top_n=2,
        follower_data_available=False,
    )

    assert "unknown_like" not in [r.reel.code for r in control]
    assert [r.reel.code for r in control] == ["known_low"]
