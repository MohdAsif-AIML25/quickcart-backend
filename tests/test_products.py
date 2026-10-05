"""RBAC, admin product CRUD, public catalogue, and the Redis cache."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from redis.exceptions import RedisError

from app.core.redis_client import redis_client

PRODUCT = {
    "name": "Mechanical Keyboard",
    "description": "Blue switches",
    "price": "2499.50",
    "stock": 5,
    "category": "Electronics",
}


# --- RBAC -------------------------------------------------------------------


def test_admin_can_create_product(client: TestClient, admin_headers: dict) -> None:
    response = client.post("/admin/products", json=PRODUCT, headers=admin_headers)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Mechanical Keyboard"
    assert body["price"] == "2499.50"  # Decimal, not float: no rounding errors
    assert body["category"] == "electronics"  # normalised to lower case
    assert body["is_active"] is True


def test_normal_user_cannot_create_product(client: TestClient, user_headers: dict) -> None:
    response = client.post("/admin/products", json=PRODUCT, headers=user_headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_anonymous_cannot_create_product(client: TestClient) -> None:
    assert client.post("/admin/products", json=PRODUCT).status_code == 401


def test_normal_user_cannot_update_or_delete_product(
    client: TestClient, user_headers: dict, create_product: Callable[..., dict]
) -> None:
    product = create_product()

    patch = client.patch(f"/admin/products/{product['id']}", json={"stock": 0}, headers=user_headers)
    delete = client.delete(f"/admin/products/{product['id']}", headers=user_headers)

    assert patch.status_code == delete.status_code == 403


# --- Validation -------------------------------------------------------------


def test_create_product_rejects_invalid_values(client: TestClient, admin_headers: dict) -> None:
    for bad in ({"price": "0"}, {"price": "-5"}, {"stock": -1}, {"name": "   "}, {"price": "9.999"}):
        response = client.post("/admin/products", json={**PRODUCT, **bad}, headers=admin_headers)
        assert response.status_code == 422, bad


# --- Update / delete --------------------------------------------------------


def test_patch_changes_only_the_fields_sent(
    client: TestClient, admin_headers: dict, create_product: Callable[..., dict]
) -> None:
    product = create_product(name="Old Name", stock=10)

    response = client.patch(
        f"/admin/products/{product['id']}", json={"name": "New Name"}, headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "New Name"
    assert response.json()["stock"] == 10  # untouched


def test_patch_rejects_explicit_null(
    client: TestClient, admin_headers: dict, create_product: Callable[..., dict]
) -> None:
    product = create_product()

    response = client.patch(
        f"/admin/products/{product['id']}", json={"name": None}, headers=admin_headers
    )

    assert response.status_code == 422


def test_patch_unknown_product_returns_404(client: TestClient, admin_headers: dict) -> None:
    response = client.patch("/admin/products/9999", json={"stock": 1}, headers=admin_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_delete_is_soft_and_hides_product_from_catalogue(
    client: TestClient, admin_headers: dict, create_product: Callable[..., dict]
) -> None:
    product = create_product()

    response = client.delete(f"/admin/products/{product['id']}", headers=admin_headers)

    assert response.status_code == 204
    assert client.get("/products").json()["total"] == 0
    # The row still exists, so the admin can re-activate it and old orders stay valid
    restored = client.patch(
        f"/admin/products/{product['id']}", json={"is_active": True}, headers=admin_headers
    )
    assert restored.status_code == 200


# --- Public catalogue -------------------------------------------------------


def test_list_products_is_public_and_paginated(
    client: TestClient, create_product: Callable[..., dict]
) -> None:
    for index in range(1, 6):
        create_product(name=f"Product {index}")

    response = client.get("/products", params={"page": 2, "limit": 2})

    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body["items"]] == ["Product 3", "Product 4"]
    assert (body["page"], body["limit"], body["total"], body["pages"]) == (2, 2, 5, 3)


def test_page_beyond_the_end_is_empty_not_an_error(
    client: TestClient, create_product: Callable[..., dict]
) -> None:
    create_product()

    body = client.get("/products", params={"page": 99}).json()

    assert body["items"] == []
    assert body["total"] == 1


def test_category_filter_is_case_insensitive(
    client: TestClient, create_product: Callable[..., dict]
) -> None:
    create_product(name="Mouse", category="electronics")
    create_product(name="Notebook", category="stationery")

    body = client.get("/products", params={"category": "Electronics"}).json()

    assert [item["name"] for item in body["items"]] == ["Mouse"]


def test_search_matches_name_and_description(
    client: TestClient, create_product: Callable[..., dict]
) -> None:
    create_product(name="Wireless Mouse", description="2.4 GHz")
    create_product(name="Keyboard", description="Wireless and silent")
    create_product(name="Notebook", description="200 pages")

    body = client.get("/products", params={"search": "wireless"}).json()

    assert {item["name"] for item in body["items"]} == {"Wireless Mouse", "Keyboard"}


def test_search_treats_percent_as_a_literal_character(
    client: TestClient, create_product: Callable[..., dict]
) -> None:
    create_product(name="Mouse")
    create_product(name="50% Off Bundle")

    body = client.get("/products", params={"search": "%"}).json()

    # Without escaping, "%" would be a wildcard and match every product
    assert [item["name"] for item in body["items"]] == ["50% Off Bundle"]


def test_invalid_pagination_returns_422(client: TestClient) -> None:
    assert client.get("/products", params={"limit": 500}).status_code == 422
    assert client.get("/products", params={"page": 0}).status_code == 422


# --- Redis cache ------------------------------------------------------------


def test_second_identical_request_is_served_from_cache(
    client: TestClient, create_product: Callable[..., dict]
) -> None:
    create_product()

    first = client.get("/products")
    second = client.get("/products")

    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "HIT"
    assert first.json() == second.json()


def test_different_query_parameters_use_different_cache_entries(
    client: TestClient, create_product: Callable[..., dict]
) -> None:
    create_product()
    client.get("/products")

    assert client.get("/products", params={"limit": 5}).headers["X-Cache"] == "MISS"


def test_cache_is_invalidated_when_a_product_changes(
    client: TestClient, admin_headers: dict, create_product: Callable[..., dict]
) -> None:
    product = create_product(name="Old Name")
    client.get("/products")
    assert client.get("/products").headers["X-Cache"] == "HIT"

    client.patch(f"/admin/products/{product['id']}", json={"name": "New Name"}, headers=admin_headers)
    after_update = client.get("/products")

    assert after_update.headers["X-Cache"] == "MISS"
    assert after_update.json()["items"][0]["name"] == "New Name"  # no stale data


def test_catalogue_still_works_when_redis_is_down(
    client: TestClient, create_product: Callable[..., dict], monkeypatch
) -> None:
    """Graceful degradation: the cache is an optimisation, not a dependency."""
    create_product()

    def broken(*args: object, **kwargs: object):
        raise RedisError("redis is down")

    monkeypatch.setattr(redis_client, "get", broken)
    monkeypatch.setattr(redis_client, "set", broken)

    response = client.get("/products")

    assert response.status_code == 200
    assert response.json()["total"] == 1
