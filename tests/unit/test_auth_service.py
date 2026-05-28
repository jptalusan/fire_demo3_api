"""Unit tests for backend.services.auth."""

import pytest
from jose import JWTError

from backend.services import auth as auth_svc


def test_hash_and_verify_password_roundtrip():
    h = auth_svc.hash_password("supersecret")
    assert h != "supersecret"
    assert auth_svc.verify_password("supersecret", h)
    assert not auth_svc.verify_password("wrong", h)


def test_token_roundtrip():
    token = auth_svc.create_token(user_id=42)
    assert auth_svc._decode_user_id(token) == 42


def test_invalid_token_raises():
    with pytest.raises(JWTError):
        auth_svc._decode_user_id("not.a.real.token")


def test_extract_token_bearer():
    assert auth_svc._extract_token("Bearer abc123") == "abc123"
    assert auth_svc._extract_token("bearer abc123") == "abc123"
    assert auth_svc._extract_token("Basic abc123") is None
    assert auth_svc._extract_token("") is None
    assert auth_svc._extract_token(None) is None


def test_password_truncated_to_bcrypt_limit():
    long_pwd = "x" * 200
    h = auth_svc.hash_password(long_pwd)
    assert auth_svc.verify_password(long_pwd, h)
