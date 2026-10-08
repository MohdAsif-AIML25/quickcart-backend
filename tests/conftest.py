"""Shared pytest fixtures for the QuickCart test suite.

The tests run against a REAL PostgreSQL database and a REAL Redis instance,
because the most important behaviour in this project (row locks, constraints,
cache invalidation, rate limiting) cannot be proven with fakes.

IMPORTANT: the environment variables below are set BEFORE anything from `app`
is imported. `app.database.session` and `app.core.redis_client` read their
settings at import time, so the order of the lines in this file matters.
"""

import itertools
import os
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://quickcart:quickcart_dev_password@localhost:5433/quickcart_test",
)
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["REDIS_URL"] = TEST_REDIS_URL
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="quickcart-test-uploads-")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-never-used-outside-pytest-0123456789")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.redis_client import redis_client  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.database.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, User  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PASSWORD = "StrongPass123"

AuthHeaders = dict[str, str]


def _create_test_database_if_missing() -> None:
    url = make_url(TEST_DATABASE_URL)
    # Safety net: these tests TRUNCATE every table. Never point them at real data.
    if not (url.database or "").endswith("_test"):
        raise RuntimeError(
            f"Refusing to run tests against database '{url.database}'. "
            "The test database name must end with '_test'."
        )
    admin_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
            )
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _prepare_database() -> Iterator[None]:
    """Once per test run: build a fresh schema by running the real Alembic migrations.

    Using the migrations (not `Base.metadata.create_all`) means a broken
    migration fails the test suite instead of failing in production.
    """
    _create_test_database_if_missing()
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))

    alembic_config = Config()  # no .ini file -> Alembic does not touch our logging setup
    alembic_config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    command.upgrade(alembic_config, "head")

    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_state() -> None:
    """Before every test: empty all tables and the Redis test database.

    Each test starts from zero, so tests cannot depend on each other or on
    the order in which they run.
    """
    table_names = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))
    redis_client.flushdb()  # clears the product cache and the rate-limit counters


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db() -> Iterator[Session]:
    """A separate session for arranging data and checking results directly."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def password_hash() -> str:
    """bcrypt is slow on purpose, so hash the default password only once per run."""
    return hash_password(DEFAULT_PASSWORD)


@pytest.fixture
def make_user(db: Session, password_hash: str) -> Callable[..., AuthHeaders]:
    """Factory: insert a user and return ready-to-use Authorization headers.

    The user is written straight to the database and the token is minted
    directly. This keeps the tests fast and does not use up the login rate
    limit. The real register/login endpoints are covered in test_auth.py.
    """
    counter = itertools.count(1)

    def _make_user(role: str = "user", email: str | None = None) -> AuthHeaders:
        user = User(
            email=email or f"{role}{next(counter)}@example.com",
            hashed_password=password_hash,
            full_name=f"Test {role.title()}",
            role=role,
        )
        db.add(user)
        db.commit()
        return {"Authorization": f"Bearer {create_access_token(user.id)}"}

    return _make_user


@pytest.fixture
def user_headers(make_user: Callable[..., AuthHeaders]) -> AuthHeaders:
    return make_user(role="user")


@pytest.fixture
def admin_headers(make_user: Callable[..., AuthHeaders]) -> AuthHeaders:
    return make_user(role="admin")


@pytest.fixture
def create_product(client: TestClient, admin_headers: AuthHeaders) -> Callable[..., dict]:
    """Factory: create a product through the real admin API and return its JSON."""

    def _create_product(**overrides: object) -> dict:
        payload = {
            "name": "Wireless Mouse",
            "description": "Ergonomic 2.4 GHz wireless mouse",
            "price": "799.00",
            "stock": 10,
            "category": "electronics",
        }
        payload.update(overrides)
        response = client.post("/admin/products", json=payload, headers=admin_headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _create_product


@pytest.fixture
def checkout_body() -> dict:
    """A valid POST /orders/checkout body. Each test gets its own copy to change."""
    return {
        "shipping_address": {
            "recipient_name": "Asha Verma",
            "phone": "+91 98765 43210",
            "address_line1": "221B MG Road",
            "address_line2": "Near City Mall",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560001",
            "country": "India",
        },
        "payment_method": "cod",
    }


@pytest.fixture
def place_order(client: TestClient, checkout_body: dict) -> Callable[..., dict]:
    """Factory: put one product in the buyer's cart, check out, return the order JSON."""

    def _place_order(headers: AuthHeaders, product_id: int, quantity: int = 1) -> dict:
        added = client.post(
            "/cart/items", json={"product_id": product_id, "quantity": quantity}, headers=headers
        )
        assert added.status_code == 201, added.text
        response = client.post("/orders/checkout", json=checkout_body, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _place_order
