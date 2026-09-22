import importlib
import os

os.environ.setdefault("APIFY_TOKEN", "test-token")

import pytest


collector = importlib.import_module("app.api.reels_collector")


def make_reel(code, caption, *, score=1.0):
    return {
        "id": code,
        "code": code,
        "caption": caption,
        "is_video": True,
        "video_url": f"https://example.com/{code}.mp4",
        "ig_play_count": int(score * 1000),
        "like_count": int(score * 100),
        "comment_count": 10,
        "taken_at": 1770000000,
    }


@pytest.mark.parametrize(
    ("caption", "expected"),
    [
        ("성수 신상 카페 디저트 추천 #성수동카페", True),
        ("완전 다른 팝업 전시 소개 #성수동카페", False),
        ("성수동 소금빵 베이커리 추천", True),
        ("부산 해운대 맛집 추천 #성수동카페", False),
    ],
)
def test_keyword_relevance_for_region_category_keyword(caption, expected):
    is_relevant, _score, _terms = collector.calculate_keyword_relevance({"caption": caption}, "성수동카페")

    assert is_relevant is expected


def test_food_synonym_query_matches_local_restaurant_caption():
    is_relevant, score, terms = collector.calculate_keyword_relevance(
        {"caption": "광주 상무지구 오마카세 맛집에서 저녁 메뉴 먹고 왔어요"},
        "광주 식사",
    )

    assert is_relevant is True
    assert score > 0
    assert "광주" in terms


def test_process_reels_excludes_hashtag_only_keyword_match():
    items = [
        make_reel("bad", "부산 해운대 맛집 추천 #성수동카페", score=50),
        make_reel("good", "성수 신상 카페 디저트 추천", score=1),
    ]

    processed = collector.process_reels(items, "성수동카페")

    assert [reel["code"] for reel in processed] == ["good"]
    assert processed[0]["keyword_relevance_score"] > 0


def test_download_skips_irrelevant_and_failures_until_target_count(tmp_path, monkeypatch):
    attempted = []

    def fake_download(video_url, code, save_dir="videos"):
        attempted.append(code)
        if code == "fail":
            raise RuntimeError("network failed")
        path = tmp_path / f"{code}.mp4"
        path.write_bytes(b"video")
        return str(path)

    monkeypatch.setattr(collector, "download_reel_video", fake_download)

    reels = [
        make_reel("bad", "완전 다른 팝업 전시 소개 #성수동카페"),
        make_reel("fail", "성수 카페 커피 추천"),
        make_reel("ok1", "성수 카페 디저트 추천"),
        make_reel("ok2", "성수동 소금빵 베이커리 추천"),
        make_reel("ok3", "성수 카페 말차 수플레 추천"),
        make_reel("ok4", "성수동 카페 커피 추천"),
        make_reel("ok5", "성수 카페 타르트 디저트 추천"),
        make_reel("extra", "성수 카페 브런치 추천"),
    ]

    downloaded = collector.download_top_reel_videos(
        reels,
        save_dir=str(tmp_path),
        keyword="성수동카페",
        target_count=5,
    )

    assert [reel["code"] for reel in downloaded] == ["ok1", "ok2", "ok3", "ok4", "ok5"]
    assert "bad" not in attempted
    assert "fail" in attempted
    assert "extra" not in attempted


def test_top_reels_does_not_repeat_when_actor_returns_less_than_requested(monkeypatch):
    calls = []
    items = [make_reel(f"item-{index}", f"광주 맛집 메뉴 추천 {index}") for index in range(4)]

    def fake_get_reels_data(keyword, max_items):
        calls.append((keyword, max_items))
        return items

    monkeypatch.setattr(collector, "get_reels_data", fake_get_reels_data)
    result = collector.get_top_reels("광주 맛집", max_items=45, top_n=12)

    assert len(result) == 4
    assert calls == [("광주 맛집", 45)]
