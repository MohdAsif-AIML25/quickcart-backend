import os

# Settings() requires a JWT secret. Tests must also run without a local .env
# (for example in GitHub Actions), so give them a throwaway value.
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-not-for-production-0123456789")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
