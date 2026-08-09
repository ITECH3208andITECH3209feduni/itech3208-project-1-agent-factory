# tests/test_auth.py — agent/auth.py (PROJ-354, PROJ-349)
import time

import pytest

from agent import auth


@pytest.fixture(autouse=True)
def _fresh_auth_db(tmp_path, monkeypatch):
    """Give every test its own SQLite file so users created in one
    test never leak into another."""
    monkeypatch.setattr(auth, "AUTH_DB", str(tmp_path / "auth.db"))


def test_register_and_login():
    auth.register_user("dilraj", "supersecret123")
    auth.verify_login("dilraj", "supersecret123")  # no exception = success


def test_duplicate_username_rejected():
    auth.register_user("dilraj", "supersecret123")
    with pytest.raises(auth.AuthError):
        auth.register_user("dilraj", "anotherpassword")


def test_short_username_rejected():
    with pytest.raises(auth.AuthError):
        auth.register_user("ab", "longenoughpassword")


def test_short_password_rejected():
    with pytest.raises(auth.AuthError):
        auth.register_user("newuser", "short")


def test_wrong_password_rejected():
    auth.register_user("dilraj", "supersecret123")
    with pytest.raises(auth.AuthError):
        auth.verify_login("dilraj", "wrongpassword")


def test_nonexistent_user_rejected():
    with pytest.raises(auth.AuthError):
        auth.verify_login("ghost", "whatever123")


def test_session_token_round_trip():
    token = auth.create_session_token("dilraj")
    assert auth.verify_session_token(token) == "dilraj"


def test_tampered_token_rejected():
    token = auth.create_session_token("dilraj")
    tampered = token[:-4] + "abcd"
    assert auth.verify_session_token(tampered) is None


def test_expired_token_rejected(monkeypatch):
    monkeypatch.setattr(auth, "SESSION_TTL_SECONDS", -10)
    expired_token = auth.create_session_token("dilraj")
    assert auth.verify_session_token(expired_token) is None


@pytest.mark.parametrize("bad_token", ["not-a-real-token", "", None])
def test_garbage_token_rejected(bad_token):
    assert auth.verify_session_token(bad_token) is None
