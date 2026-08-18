from datetime import UTC, datetime, timedelta

from app.pipeline.collect import (
    dedupe_by_caption_similarity,
    extract_hashtags,
    filter_recent,
    is_relevant,
)
from app.schemas.collect import RawReel

NOW = datetime(2026, 8, 6, tzinfo=UTC)


def _reel(**overrides) -> RawReel:
    defaults = dict(
        code="Cabc123",
        url="https://instagram.com/reel/Cabc123",
        username="cafe_seongsu",
        caption="",
        hashtags=[],
        taken_at=NOW,
    )
    defaults.update(overrides)
    return RawReel(**defaults)


def test_extract_hashtags_finds_all_tags():
    tags = extract_hashtags("성수동 카페 신메뉴 #성수동카페 #카페추천 #오늘의커피")
    assert tags == ["#성수동카페", "#카페추천", "#오늘의커피"]


def test_extract_hashtags_empty_when_none():
    assert extract_hashtags("해시태그 없는 캡션") == []


def test_filter_recent_keeps_within_30_days():
    fresh = _reel(code="fresh", taken_at=NOW - timedelta(days=10))
    old = _reel(code="old", taken_at=NOW - timedelta(days=31))
    boundary = _reel(code="boundary", taken_at=NOW - timedelta(days=30))

    result = filter_recent([fresh, old, boundary], now=NOW)

    codes = {r.code for r in result}
    assert codes == {"fresh", "boundary"}


def test_filter_recent_handles_naive_datetime():
    naive_old = _reel(code="naive_old", taken_at=datetime(2026, 1, 1))
    result = filter_recent([naive_old], now=NOW)
    assert result == []


def test_is_relevant_short_keyword_requires_full_match():
    # "성수동카페"는 어절 1개(<=3) → 전부 매칭해야 함
    reel_with = _reel(caption="성수동카페 다녀왔어요")
    reel_without = _reel(caption="홍대 맛집 다녀왔어요")

    assert is_relevant("성수동카페", reel_with) is True
    assert is_relevant("성수동카페", reel_without) is False


def test_is_relevant_checks_hashtags():
    reel = _reel(caption="오늘의 커피", hashtags=["#성수동카페"], username="random_user")
    assert is_relevant("성수동카페", reel) is True


def test_is_relevant_checks_username():
    # 캡션·해시태그엔 없고 계정명에만 있는 경우
    reel = _reel(caption="오늘의 커피", hashtags=[], username="성수동카페_official")
    assert is_relevant("성수동카페", reel) is True

    reel_without = _reel(caption="오늘의 커피", hashtags=[], username="random_user")
    assert is_relevant("성수동카페", reel_without) is False


def test_is_relevant_long_keyword_needs_75_percent():
    # 어절 4개 > 3 → 75% 이상(4개 중 3개) 매칭이면 통과
    keyword = "성수동 원두 로스팅 카페"
    # 성수동/원두/로스팅 매칭(카페는 없음) = 3/4
    reel_3_of_4 = _reel(caption="성수동에서 원두 로스팅 하는 곳")
    reel_2_of_4 = _reel(caption="성수동 카페 투어")  # 성수동/카페만 매칭 = 2/4

    assert is_relevant(keyword, reel_3_of_4) is True
    assert is_relevant(keyword, reel_2_of_4) is False


def test_is_relevant_empty_keyword_is_false():
    assert is_relevant("", _reel(caption="아무거나")) is False


def test_dedupe_keeps_first_occurrence_of_similar_captions():
    a = _reel(code="a", caption="성수동 카페 신메뉴 나왔어요! 꼭 드셔보세요")
    b = _reel(code="b", caption="성수동 카페 신메뉴 나왔어요!! 꼭 드셔보세요~")  # 사실상 동일
    c = _reel(code="c", caption="완전히 다른 내용의 캡션입니다 아무 관련 없음")

    result = dedupe_by_caption_similarity([a, b, c])

    codes = [r.code for r in result]
    assert codes == ["a", "c"]


def test_dedupe_respects_custom_threshold():
    # SequenceMatcher ratio ≈ 0.72 — 0.5와 0.82 사이라 임계값에 따라 결과가 갈린다
    a = _reel(code="a", caption="완전 좋았던 하루였어요 감사합니다")
    b = _reel(code="b", caption="진짜 좋았던 하루였어요 고맙습니다")

    # 임계값을 낮추면 비슷한 것으로 묶여서 하나만 남는다
    result_loose = dedupe_by_caption_similarity([a, b], threshold=0.5)
    assert len(result_loose) == 1

    # 기본 임계값(0.82)보다 낮은 유사도라 서로 다른 캡션으로 남는다
    result_strict = dedupe_by_caption_similarity([a, b])
    assert len(result_strict) == 2
