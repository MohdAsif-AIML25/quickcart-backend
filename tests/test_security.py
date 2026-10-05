"""Unit tests for password hashing and JWT helpers (no HTTP involved)."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_is_hashed_and_verifiable() -> None:
    hashed = hash_password("StrongPass123")

    assert hashed != "StrongPass123"
    assert verify_password("StrongPass123", hashed) is True
    assert verify_password("WrongPass123", hashed) is False


def test_same_password_gives_different_hashes() -> None:
    # bcrypt adds a random salt, so equal passwords must not produce equal hashes
    assert hash_password("StrongPass123") != hash_password("StrongPass123")


def test_password_longer_than_72_bytes_is_rejected() -> None:
    hashed = hash_password("StrongPass123")
    assert verify_password("x" * 73, hashed) is False


def test_access_token_round_trip() -> None:
    token = create_access_token(42)
    assert decode_token(token, expected_type="access") == 42


def test_refresh_token_cannot_be_used_as_access_token() -> None:
    token = create_refresh_token(42)
    with pytest.raises(UnauthorizedError, match="Invalid token type"):
        decode_token(token, expected_type="access")


def test_expired_token_is_rejected() -> None:
    settings = get_settings()
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    expired = jwt.encode(
        {"sub": "42", "type": "access", "iat": past - timedelta(minutes=15), "exp": past},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(UnauthorizedError, match="expired"):
        decode_token(expired, expected_type="access")


def test_token_signed_with_another_key_is_rejected() -> None:
    forged = jwt.encode(
        {"sub": "42", "type": "access", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "an-attacker-key-that-is-not-our-secret-0123456789",
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedError, match="Invalid token"):
        decode_token(forged, expected_type="access")


def test_garbage_token_is_rejected() -> None:
    with pytest.raises(UnauthorizedError):
        decode_token("not-a-jwt", expected_type="access")
