import json

import pytest

from app.core.local_auth import register
from app.core.privacy import user_namespace
from scripts.adopt_legacy_data import adopt, legacy_items


def _setup(tmp_path):
    base = tmp_path / "user_reels"
    base.mkdir()
    (base / "content_projects.json").write_text('[{"id":"1"}]', encoding="utf-8")
    (base / "market_snapshots").mkdir()
    (base / "market_snapshots" / "a.json").write_text("{}", encoding="utf-8")
    (base / "api_usage.jsonl").write_text("{}\n", encoding="utf-8")
    (base / "jobs.sqlite3").write_text("x", encoding="utf-8")
    (base / "guests").mkdir()
    (base / ("a" * 20)).mkdir()  # another member's namespace
    session = register(base / "accounts.json", "me@example.com", "pw-12345678")
    return base, base / user_namespace(session["user_id"])


def test_only_member_content_is_listed(tmp_path):
    base, _ = _setup(tmp_path)
    assert [item.name for item in legacy_items(base)] == ["content_projects.json", "market_snapshots"]


def test_dry_run_changes_nothing_and_apply_copies_without_touching_originals(tmp_path):
    base, target = _setup(tmp_path)
    assert adopt(base, "me@example.com", apply=False) == ["복사 예정: content_projects.json", "복사 예정: market_snapshots"]
    assert not target.exists()
    adopt(base, "ME@example.com ", apply=True)
    assert json.loads((target / "content_projects.json").read_text(encoding="utf-8")) == [{"id": "1"}]
    assert (target / "market_snapshots" / "a.json").is_file()
    assert (base / "content_projects.json").is_file(), "original must stay"


def test_existing_files_are_not_overwritten_and_unknown_email_fails(tmp_path):
    base, target = _setup(tmp_path)
    target.mkdir()
    (target / "content_projects.json").write_text("mine", encoding="utf-8")
    assert "건너뜀(이미 있음): content_projects.json" in adopt(base, "me@example.com", apply=True)
    assert (target / "content_projects.json").read_text(encoding="utf-8") == "mine"
    with pytest.raises(SystemExit):
        adopt(base, "nobody@example.com", apply=False)
