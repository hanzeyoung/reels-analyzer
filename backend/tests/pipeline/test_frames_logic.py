from app.pipeline.frames import (
    FALLBACK_SPLITS,
    _parse_scene_change_times,
    build_cut_boundaries,
)

SHOWINFO_STDERR = """
[Parsed_showinfo_1 @ 0x1] n:   0 pts:      0 pts_time:0        duration: 40
[Parsed_showinfo_1 @ 0x1] n:   1 pts:   3000 pts_time:3.0      duration: 40
[Parsed_showinfo_1 @ 0x1] n:   2 pts:   9500 pts_time:9.5      duration: 40
frame=  120 fps=0.0 q=-1.0 Lsize=N/A time=00:00:12.00 bitrate=N/A speed=245x
"""


def test_parse_scene_change_times_extracts_pts_time():
    times = _parse_scene_change_times(SHOWINFO_STDERR)
    assert times == [0.0, 3.0, 9.5]


def test_parse_scene_change_times_empty_when_no_showinfo():
    assert _parse_scene_change_times("no showinfo here") == []


def test_build_cut_boundaries_uses_scene_times_when_enough_cuts():
    # 경계 3.0, 9.5 → (0,3.0),(3.0,9.5),(9.5,12.0) = 3구간, MIN_CUTS(3) 충족
    segments = build_cut_boundaries([3.0, 9.5], duration=12.0)
    assert segments == [(0.0, 3.0), (3.0, 9.5), (9.5, 12.0)]


def test_build_cut_boundaries_ignores_boundaries_outside_duration():
    # duration(12.0) 밖의 999.0/-1.0은 무시 → 유효 경계는 3.0 하나뿐 → 구간 2개 < MIN_CUTS(3)
    # → 폴백 5분할
    segments = build_cut_boundaries([3.0, 999.0, -1.0], duration=12.0)
    assert len(segments) == FALLBACK_SPLITS


def test_build_cut_boundaries_falls_back_to_5_splits_when_too_few_cuts():
    # scene 경계가 아예 없는 롱테이크 릴스
    segments = build_cut_boundaries([], duration=20.0)
    assert len(segments) == FALLBACK_SPLITS
    assert segments[0] == (0.0, 4.0)
    assert segments[-1] == (16.0, 20.0)
    for start, end in segments:
        assert start < end


def test_build_cut_boundaries_falls_back_when_fewer_than_min_cuts():
    # 경계 1개 → 구간 2개 < MIN_CUTS(3) → 폴백
    segments = build_cut_boundaries([5.0], duration=10.0)
    assert len(segments) == FALLBACK_SPLITS
