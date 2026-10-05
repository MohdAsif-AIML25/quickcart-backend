"""Registration, login, refresh, /me, and the login rate limiter."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.redis_client import redis_client
from app.models import User

REGISTER_PAYLOAD = {
    "email": "asif@example.com",
    "password": "StrongPass123",
    "full_name": "Mohammad Asif",
}


def _register(client: TestClient, **overrides: str):
    return client.post("/auth/register", json={**REGISTER_PAYLOAD, **overrides})


def _login(client: TestClient, email: str = "asif@example.com", password: str = "StrongPass123"):
    # OAuth2 password flow: form data, and the email goes in the `username` field
    return client.post("/auth/login", data={"username": email, "password": password})


# --- Register ---------------------------------------------------------------


def test_register_creates_user(client: TestClient, db: Session) -> None:
    response = _register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "asif@example.com"
    assert body["role"] == "user"
    assert "password" not in body and "hashed_password" not in body

    stored = db.scalar(select(User).where(User.email == "asif@example.com"))
    assert stored is not None
    assert stored.hashed_password != "StrongPass123"  # never stored in plain text


def test_register_duplicate_email_returns_409(client: TestClient) -> None:
    _register(client)
    response = _register(client, email="ASIF@example.com")  # email is case-insensitive

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_register_rejects_short_password_and_bad_email(client: TestClient) -> None:
    assert _register(client, password="short").status_code == 422
    assert _register(client, email="not-an-email").status_code == 422


# --- Login ------------------------------------------------------------------


def test_login_returns_token_pair(client: TestClient) -> None:
    _register(client)
    response = _login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]
    assert body["access_token"] != body["refresh_token"]


def test_login_gives_same_error_for_unknown_email_and_wrong_password(client: TestClient) -> None:
    _register(client)

    wrong_password = _login(client, password="WrongPass123")
    unknown_email = _login(client, email="nobody@example.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    # Identical bodies -> an attacker cannot discover which emails are registered
    assert wrong_password.json() == unknown_email.json()


def test_login_disabled_account_returns_403(client: TestClient, db: Session) -> None:
    _register(client)
    user = db.scalar(select(User).where(User.email == "asif@example.com"))
    user.is_active = False
    db.commit()

    assert _login(client).status_code == 403


# --- /auth/me ---------------------------------------------------------------


def test_me_returns_current_user(client: TestClient) -> None:
    _register(client)
    access_token = _login(client).json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})

    assert response.status_code == 200
    assert response.json()["email"] == "asif@example.com"


def test_me_without_token_returns_401(client: TestClient) -> None:
    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_with_invalid_token_returns_401(client: TestClient) -> None:
    response = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_me_with_token_of_deactivated_user_returns_401(
    client: TestClient, db: Session, make_user: Callable[..., dict]
) -> None:
    """The token is genuine and not expired, but the account behind it was switched off."""
    headers = make_user(email="blocked@example.com")
    user = db.scalar(select(User).where(User.email == "blocked@example.com"))
    user.is_active = False
    db.commit()

    response = client.get("/auth/me", headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "User not found or inactive"


def test_me_with_token_of_deleted_user_returns_401(
    client: TestClient, db: Session, make_user: Callable[..., dict]
) -> None:
    """A token can outlive its user: it stays valid for 15 minutes after the row is gone."""
    headers = make_user(email="gone@example.com")
    db.execute(delete(User).where(User.email == "gone@example.com"))
    db.commit()

    response = client.get("/auth/me", headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "User not found or inactive"


# --- Refresh ----------------------------------------------------------------


def test_refresh_returns_working_access_token(client: TestClient) -> None:
    _register(client)
    refresh_token = _login(client).json()["refresh_token"]

    response = client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    new_access = response.json()["access_token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {new_access}"}).status_code == 200


def test_access_token_is_rejected_by_refresh_endpoint(client: TestClient) -> None:
    _register(client)
    access_token = _login(client).json()["access_token"]

    response = client.post("/auth/refresh", json={"refresh_token": access_token})

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid token type"


def test_refresh_token_is_rejected_as_access_token(client: TestClient) -> None:
    _register(client)
    refresh_token = _login(client).json()["refresh_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {refresh_token}"})

    assert response.status_code == 401


def test_refresh_token_of_deactivated_user_is_rejected(client: TestClient, db: Session) -> None:
    """A refresh token lives for 7 days. Without this check, a blocked user could
    keep exchanging it for new access tokens for a whole week."""
    _register(client)
    refresh_token = _login(client).json()["refresh_token"]
    user = db.scalar(select(User).where(User.email == "asif@example.com"))
    user.is_active = False
    db.commit()

    response = client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "User not found or inactive"


# --- Rate limiting ----------------------------------------------------------


def test_login_is_rate_limited(client: TestClient) -> None:
    limit = get_settings().login_rate_limit
    _register(client)

    for _ in range(limit):
        assert _login(client, password="WrongPass123").status_code == 401

    blocked = _login(client)  # even the correct password is blocked now

    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "too_many_requests"
    assert int(blocked.headers["Retry-After"]) >= 1


def test_login_still_works_when_redis_is_down(client: TestClient, monkeypatch) -> None:
    """Fail open: a Redis outage must not lock every user out."""

    def broken_pipeline(*args: object, **kwargs: object):
        raise RedisError("redis is down")

    monkeypatch.setattr(redis_client, "pipeline", broken_pipeline)
    _register(client)

    assert _login(client).status_code == 200
