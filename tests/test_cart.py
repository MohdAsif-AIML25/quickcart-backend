"""Cart: add, merge quantities, stock validation, totals, and ownership."""

from collections.abc import Callable

from fastapi.testclient import TestClient


def _add(client: TestClient, headers: dict, product_id: int, quantity: int = 1):
    return client.post(
        "/cart/items", json={"product_id": product_id, "quantity": quantity}, headers=headers
    )


def test_cart_requires_authentication(client: TestClient) -> None:
    assert client.get("/cart").status_code == 401
    assert client.post("/cart/items", json={"product_id": 1, "quantity": 1}).status_code == 401


def test_add_item_returns_line_with_subtotal(
    client: TestClient, user_headers: dict, create_product: Callable[..., dict]
) -> None:
    product = create_product(name="Mouse", price="799.00", stock=10)

    response = _add(client, user_headers, product["id"], quantity=2)

    assert response.status_code == 201
    body = response.json()
    assert body["product_name"] == "Mouse"
    assert body["quantity"] == 2
    assert body["subtotal"] == "1598.00"


def test_adding_same_product_twice_increases_quantity(
    client: TestClient, user_headers: dict, create_product: Callable[..., dict]
) -> None:
    product = create_product(stock=10)

    _add(client, user_headers, product["id"], quantity=2)
    _add(client, user_headers, product["id"], quantity=3)

    cart = client.get("/cart", headers=user_headers).json()
    assert len(cart["items"]) == 1  # one row, not two
    assert cart["items"][0]["quantity"] == 5


def test_cannot_add_more_than_available_stock(
    client: TestClient, user_headers: dict, create_product: Callable[..., dict]
) -> None:
    product = create_product(stock=3)

    assert _add(client, user_headers, product["id"], quantity=4).status_code == 409

    # The limit also applies to the total across several requests
    assert _add(client, user_headers, product["id"], quantity=2).status_code == 201
    assert _add(client, user_headers, product["id"], quantity=2).status_code == 409


def test_cannot_add_unknown_or_inactive_product(
    client: TestClient, user_headers: dict, admin_headers: dict, create_product: Callable[..., dict]
) -> None:
    product = create_product()
    client.delete(f"/admin/products/{product['id']}", headers=admin_headers)

    assert _add(client, user_headers, 9999).status_code == 404
    assert _add(client, user_headers, product["id"]).status_code == 404


def test_quantity_must_be_between_1_and_100(
    client: TestClient, user_headers: dict, create_product: Callable[..., dict]
) -> None:
    product = create_product(stock=1000)

    assert _add(client, user_headers, product["id"], quantity=0).status_code == 422
    assert _add(client, user_headers, product["id"], quantity=101).status_code == 422


def test_cart_line_cannot_exceed_100_units_across_requests(
    client: TestClient, user_headers: dict, create_product: Callable[..., dict]
) -> None:
    """60 and 60 are each valid, so the schema (422) cannot catch this: only the
    service knows the cart already holds 60. Stock is 1000, so it is not a 409 either."""
    product = create_product(stock=1000)

    first = _add(client, user_headers, product["id"], quantity=60)
    second = _add(client, user_headers, product["id"], quantity=60)  # 60 + 60 = 120 > 100

    assert first.status_code == 201
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "bad_request"
    assert "Maximum 100 units" in second.json()["error"]["message"]
    # The rejected request changed nothing
    assert client.get("/cart", headers=user_headers).json()["items"][0]["quantity"] == 60

    # Boundary: exactly 100 is allowed (the rule is "> 100", not ">= 100")
    assert _add(client, user_headers, product["id"], quantity=40).status_code == 201
    assert client.get("/cart", headers=user_headers).json()["items"][0]["quantity"] == 100


def test_cart_totals_are_correct(
    client: TestClient, user_headers: dict, create_product: Callable[..., dict]
) -> None:
    mouse = create_product(name="Mouse", price="799.00")
    cable = create_product(name="Cable", price="149.50")
    _add(client, user_headers, mouse["id"], quantity=2)
    _add(client, user_headers, cable["id"], quantity=3)

    cart = client.get("/cart", headers=user_headers).json()

    assert cart["total_items"] == 5
    assert cart["total_amount"] == "2046.50"  # 2 * 799.00 + 3 * 149.50


def test_empty_cart_has_zero_totals(client: TestClient, user_headers: dict) -> None:
    cart = client.get("/cart", headers=user_headers).json()

    assert cart["items"] == []
    assert cart["total_items"] == 0
    assert float(cart["total_amount"]) == 0


def test_remove_item(
    client: TestClient, user_headers: dict, create_product: Callable[..., dict]
) -> None:
    product = create_product()
    item_id = _add(client, user_headers, product["id"]).json()["id"]

    assert client.delete(f"/cart/items/{item_id}", headers=user_headers).status_code == 204
    assert client.get("/cart", headers=user_headers).json()["items"] == []
    # Deleting it again -> it no longer exists
    assert client.delete(f"/cart/items/{item_id}", headers=user_headers).status_code == 404


def test_carts_are_private_to_each_user(
    client: TestClient, make_user: Callable[..., dict], create_product: Callable[..., dict]
) -> None:
    alice, bob = make_user(), make_user()
    product = create_product()
    alice_item_id = _add(client, alice, product["id"]).json()["id"]

    # Bob cannot see Alice's cart...
    assert client.get("/cart", headers=bob).json()["items"] == []
    # ...and cannot delete her item. 404 (not 403) does not reveal that the item exists.
    assert client.delete(f"/cart/items/{alice_item_id}", headers=bob).status_code == 404
    assert len(client.get("/cart", headers=alice).json()["items"]) == 1
