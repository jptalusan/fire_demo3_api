"""Extra unit tests for backend.services.auth: JWT claims, expiry, signatures, normalization."""

from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt
from jose.exceptions import JWTError

from backend.config import settings
from backend.services import auth as auth_svc


# ---------- JWT claims ----------

def test_token_has_sub_and_exp_roughly_6h():
    token = auth_svc.create_token(user_id=7)
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[auth_svc.ALGORITHM])
    assert payload["sub"] == "7"
    assert "exp" in payload and "iat" in payload
    ttl = payload["exp"] - payload["iat"]
    # ACCESS_TOKEN_TTL_HOURS == 6 -> 21600s, allow small clock slack.
    assert abs(ttl - auth_svc.ACCESS_TOKEN_TTL_HOURS * 3600) <= 5


def test_expired_token_rejected():
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    token = jwt.encode(
        {"sub": "1", "exp": past, "iat": past - timedelta(hours=1)},
        settings.SECRET_KEY,
        algorithm=auth_svc.ALGORITHM,
    )
    with pytest.raises(JWTError):
        auth_svc._decode_user_id(token)


def test_bad_signature_rejected():
    token = jwt.encode({"sub": "1"}, "a-different-secret", algorithm=auth_svc.ALGORITHM)
    with pytest.raises(JWTError):
        auth_svc._decode_user_id(token)


def test_token_missing_sub_raises_value_error():
    token = jwt.encode(
        {"exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        settings.SECRET_KEY,
        algorithm=auth_svc.ALGORITHM,
    )
    with pytest.raises(ValueError):
        auth_svc._decode_user_id(token)


# ---------- password normalization / verification ----------

def test_verify_wrong_password_fails():
    h = auth_svc.hash_password("correct-horse")
    assert not auth_svc.verify_password("battery-staple", h)


def test_bcrypt_72_byte_truncation_equivalence():
    """bcrypt only uses the first 72 bytes; two strings sharing that prefix verify."""
    base = "p" * 72
    h = auth_svc.hash_password(base)
    # Same 72-byte prefix, different tail -> still verifies (documented truncation).
    assert auth_svc.verify_password(base + "EXTRA-IGNORED", h)


def test_normalize_password_accepts_bytes():
    assert auth_svc._normalize_password(b"hello") == b"hello"
    assert auth_svc._normalize_password("hello") == b"hello"


def test_normalize_password_caps_at_72_bytes():
    assert len(auth_svc._normalize_password("z" * 500)) == 72


def test_hash_then_verify_with_bytes_input():
    h = auth_svc.hash_password("unicode-é")
    assert auth_svc.verify_password("unicode-é", h)
