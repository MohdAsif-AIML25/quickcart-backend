from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"]
    assert body["version"]


def test_openapi_lists_every_router(client: TestClient) -> None:
    """Catches the classic mistake: a router was written but never included in main.py."""
    paths = client.get("/openapi.json").json()["paths"]

    for expected in (
        "/health",
        "/auth/register",
        "/auth/login",
        "/products",
        "/admin/products",
        "/cart",
        "/orders/checkout",
        "/admin/orders",
    ):
        assert expected in paths


def test_protected_route_requires_token(client: TestClient) -> None:
    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert response.headers["WWW-Authenticate"] == "Bearer"
