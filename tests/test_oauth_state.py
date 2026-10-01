import json
import threading

from app.core.oauth_state import MAX_PENDING, consume_state, issue_state


def test_state_is_single_use(tmp_path):
    path = tmp_path / "oauth_states.json"
    state = issue_state(path, "user-1")
    assert consume_state(path, state, "user-1") is True
    assert consume_state(path, state, "user-1") is False


def test_empty_unknown_and_non_string_states_are_rejected(tmp_path):
    path = tmp_path / "oauth_states.json"
    issue_state(path, "user-1")
    for bad in ("", "nope", None, 123):
        assert consume_state(path, bad, "user-1") is False
    # a missing store file must not raise or accept anything
    assert consume_state(tmp_path / "missing.json", "abc", "user-1") is False


def test_state_expires(tmp_path):
    path = tmp_path / "oauth_states.json"
    state = issue_state(path, "user-1", ttl=60, now=1_000.0)
    assert consume_state(path, state, "user-1", now=1_061.0) is False
    # an expired state stays unusable even if the clock were wrong again
    assert consume_state(path, state, "user-1", now=1_010.0) is False


def test_state_bound_to_owner_and_not_spent_by_other_user(tmp_path):
    path = tmp_path / "oauth_states.json"
    state = issue_state(path, "alice")
    assert consume_state(path, state, "bob") is False
    assert consume_state(path, state, "alice") is True


def test_only_digest_is_stored(tmp_path):
    path = tmp_path / "oauth_states.json"
    state = issue_state(path, "user-1")
    raw = path.read_text(encoding="utf-8")
    assert state not in raw
    assert all(len(key) == 64 for key in json.loads(raw))


def test_pending_states_are_capped_and_expired_ones_purged(tmp_path):
    path = tmp_path / "oauth_states.json"
    issue_state(path, "old", ttl=10, now=100.0)
    for index in range(MAX_PENDING + 20):
        issue_state(path, "user", ttl=1_000, now=200.0 + index)
    rows = json.loads(path.read_text(encoding="utf-8"))
    assert len(rows) <= MAX_PENDING
    assert all(row["owner"] == "user" for row in rows.values())


def test_concurrent_issue_keeps_every_state(tmp_path):
    path = tmp_path / "oauth_states.json"
    issued = []

    def work():
        issued.append(issue_state(path, "user"))

    threads = [threading.Thread(target=work) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert all(consume_state(path, state, "user") for state in issued)
