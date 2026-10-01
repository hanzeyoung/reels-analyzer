from app.core.signal_studies import build_signal_synthesis, build_visual_synthesis
from app.ui.workspace import _items_digest, _reel_label, _select_items, _study_identity

ITEMS = [
    {"media_id": "a", "username": "u1", "caption": "라떼아트 #카페", "views": 100, "url": "https://x/a"},
    {"media_id": "b", "username": "u2", "caption": "", "views": 50, "url": "https://x/b"},
    {"media_id": "", "username": "u3", "caption": "신메뉴 #카페", "views": 70, "url": "https://x/c"},
]


def test_select_items_keeps_input_order():
    picked = _select_items(ITEMS, ["https://x/c", "a"])
    assert [_study_identity(i) for i in picked] == ["a", "https://x/c"]


def test_select_items_empty_unknown_and_duplicate_ids():
    assert _select_items(ITEMS, []) == []
    assert _select_items(ITEMS, None) == []
    assert _select_items(ITEMS, ["nope"]) == []
    assert [i["media_id"] for i in _select_items(ITEMS, ["b", "b", "zzz"])] == ["b"]


def test_select_items_all_returns_everything():
    assert _select_items(ITEMS, [_study_identity(i) for i in ITEMS]) == ITEMS


def test_digest_changes_when_list_changes():
    assert _items_digest(ITEMS) == _items_digest(list(ITEMS))
    assert _items_digest(ITEMS) != _items_digest(ITEMS[:2])


def test_reel_label_handles_missing_fields():
    assert _reel_label({}) == "@알 수 없음 · 캡션 없음"


def test_single_reel_synthesis_does_not_raise():
    one = _select_items(ITEMS, ["a"])
    synthesis = build_signal_synthesis(one, query="카페")
    assert synthesis["sample_count"] == 1
    analysis = {"camera_angles": ["클로즈업"], "subtitle_position": "하단", "cut_speed": "빠름", "bgm_mood": "밝음"}
    visual = build_visual_synthesis({"a": analysis}, one)
    assert isinstance(visual, dict)
