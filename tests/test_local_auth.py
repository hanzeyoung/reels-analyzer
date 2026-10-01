from __future__ import annotations

import os
import threading

import pytest

from app.core import local_auth
from app.core.local_auth import (
    AuthError,
    account_count,
    authenticate,
    delete_account,
    register,
)

PW = "correct-horse-1"
BAD = "이메일 또는 비밀번호가 올바르지 않아요."


@pytest.fixture
def db(tmp_path):
    return tmp_path / "accounts.json"


def test_register_and_login(db):
    s = register(db, "a@example.com", PW)
    assert s["provider"] == "local" and len(s["user_id"]) == 32
    assert authenticate(db, "a@example.com", PW) == s


def test_email_normalized(db):
    s = register(db, "  Foo@Example.COM ", PW)
    assert s["email"] == "foo@example.com"
    assert authenticate(db, "FOO@example.com  ", PW)["user_id"] == s["user_id"]


@pytest.mark.parametrize("bad", ["", "abc", "a@b", "a b@c.com", "a@@c.com", "a@c..com", "x" * 250 + "@a.com"])
def test_bad_email(db, bad):
    with pytest.raises(AuthError, match="이메일 형식"):
        register(db, bad, PW)


def test_same_failure_message(db):
    register(db, "a@example.com", PW)
    with pytest.raises(AuthError) as e1:
        authenticate(db, "a@example.com", "wrong-password")
    with pytest.raises(AuthError) as e2:
        authenticate(db, "nobody@example.com", "wrong-password")
    assert str(e1.value) == str(e2.value) == BAD


def test_lockout_and_release(db):
    register(db, "a@example.com", PW)
    t = 1000.0
    for _ in range(5):
        with pytest.raises(AuthError, match="올바르지"):
            authenticate(db, "a@example.com", "wrong-password", now=t)
    with pytest.raises(AuthError, match="너무 많아요. 5분 뒤"):
        authenticate(db, "a@example.com", PW, now=t + 1)
    with pytest.raises(AuthError, match="1분 뒤"):
        authenticate(db, "a@example.com", PW, now=t + 290)
    assert authenticate(db, "a@example.com", PW, now=t + 301)["email"] == "a@example.com"


def test_success_resets_failures(db):
    register(db, "a@example.com", PW)
    for _ in range(4):
        with pytest.raises(AuthError):
            authenticate(db, "a@example.com", "wrong-password", now=1.0)
    authenticate(db, "a@example.com", PW, now=2.0)
    for _ in range(4):
        with pytest.raises(AuthError, match="올바르지"):
            authenticate(db, "a@example.com", "wrong-password", now=3.0)
    assert authenticate(db, "a@example.com", PW, now=4.0)


def test_duplicate(db):
    register(db, "a@example.com", PW)
    with pytest.raises(AuthError, match="이미 가입된 이메일입니다."):
        register(db, "A@example.com", PW)


@pytest.mark.parametrize(
    "pw, msg",
    [("short1", "8자 이상"), ("x" * 129, "128자 이하"), ("userName", "이메일 아이디")],
)
def test_password_policy(db, pw, msg):
    with pytest.raises(AuthError, match=msg):
        register(db, "username@example.com", pw)
    assert account_count(db) == 0


def test_no_plaintext_and_permissions(db):
    register(db, "a@example.com", PW)
    assert PW not in db.read_text(encoding="utf-8")
    if os.name != "nt":
        assert (db.stat().st_mode & 0o777) == 0o600


def test_user_id_stable(db):
    s = register(db, "a@example.com", PW)
    for _ in range(2):
        assert authenticate(db, "a@example.com", PW)["user_id"] == s["user_id"]


def test_delete_account(db):
    s = register(db, "a@example.com", PW)
    assert delete_account(db, s["user_id"]) is True
    assert delete_account(db, s["user_id"]) is False
    assert account_count(db) == 0
    with pytest.raises(AuthError, match="올바르지"):
        authenticate(db, "a@example.com", PW)


def test_missing_and_corrupt_file(db):
    assert account_count(db) == 0
    with pytest.raises(AuthError, match="올바르지"):
        authenticate(db, "a@example.com", PW)
    db.write_text("{not json", encoding="utf-8")
    assert account_count(db) == 0
    register(db, "a@example.com", PW)
    assert account_count(db) == 1
    db.write_text("[1,2]", encoding="utf-8")
    assert account_count(db) == 0


def test_concurrent_register(db):
    errors: list[Exception] = []

    def work(i: int) -> None:
        try:
            register(db, f"user{i}@example.com", PW)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert account_count(db) == 20
    assert local_auth.authenticate(db, "user7@example.com", PW)
