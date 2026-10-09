"""Checkout input: delivery address validation, payment method, and what the order stores."""

import threading
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models import Order, Product


def _add(client: TestClient, headers: dict, product_id: int, quantity: int = 1) -> None:
    response = client.post(
        "/cart/items", json={"product_id": product_id, "quantity": quantity}, headers=headers
    )
    assert response.status_code == 201, response.text


def _error_fields(response) -> set[str]:
    """The names of the fields a 422 response complains about."""
    return {error["loc"][-1] for error in response.json()["detail"]}


# --- Address snapshot -------------------------------------------------------


def test_order_stores_the_address_it_was_placed_with(
    client: TestClient, user_headers: dict, create_product: Callable[..., dict], checkout_body: dict
) -> None:
    product = create_product()
    _add(client, user_headers, product["id"])

    order = client.post("/orders/checkout", json=checkout_body, headers=user_headers).json()

    assert order["shipping_address"] == {
        "recipient_name": "Asha Verma",
        "phone": "+919876543210",  # spaces removed
        "address_line1": "221B MG Road",
        "address_line2": "Near City Mall",
        "city": "Bengaluru",
        "state": "Karnataka",
        "country": "India",
        "postal_code": "560001",
    }
    # The same address is in the order history and in the admin view
    assert client.get("/orders/me", headers=user_headers).json()[0]["shipping_address"] == order["shipping_address"]


def test_address_text_is_trimmed_and_optional_line_can_be_blank(
    client: TestClient, user_headers: dict, create_product: Callable[..., dict], checkout_body: dict
) -> None:
    product = create_product()
    _add(client, user_headers, product["id"])
    checkout_body["shipping_address"].update(recipient_name="  Asha Verma  ", address_line2="   ")

    order = client.post("/orders/checkout", json=checkout_body, headers=user_headers).json()

    assert order["shipping_address"]["recipient_name"] == "Asha Verma"
    assert order["shipping_address"]["address_line2"] is None


def test_address_line2_may_be_omitted(
    client: TestClient, user_headers: dict, create_product: Callable[..., dict], checkout_body: dict
) -> None:
    product = create_product()
    _add(client, user_headers, product["id"])
    del checkout_body["shipping_address"]["address_line2"]

    response = client.post("/orders/checkout", json=checkout_body, headers=user_headers)

    assert response.status_code == 201
    assert response.json()["shipping_address"]["address_line2"] is None


# --- Address validation -----------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("recipient_name", ""),
        ("recipient_name", "   "),
        ("recipient_name", "A"),
        ("recipient_name", "12345"),
        ("recipient_name", "x" * 101),
        ("phone", "12345"),  # too short
        ("phone", "98765abcde"),
        ("phone", "1" * 16),  # more than 15 digits
        ("phone", "98765+43210"),  # + only at the start
        ("address_line1", "ab"),
        ("address_line1", "x" * 201),
        ("address_line2", "x" * 201),
        ("city", " "),
        ("city", "560001"),
        ("state", "K"),
        ("postal_code", "56001"),  # India: must be 6 digits
        ("postal_code", "056001"),  # India: cannot start with 0
        ("postal_code", "5600!1"),
        ("country", "1ndia"),
        ("country", "I"),
    ],
)
def test_checkout_rejects_an_invalid_address_field(
    client: TestClient,
    db: Session,
    user_headers: dict,
    create_product: Callable[..., dict],
    checkout_body: dict,
    field: str,
    value: str,
) -> None:
    product = create_product(stock=10)
    _add(client, user_headers, product["id"])
    checkout_body["shipping_address"][field] = value

    response = client.post("/orders/checkout", json=checkout_body, headers=user_headers)

    assert response.status_code == 422
    assert _error_fields(response) == {field}
    # A rejected checkout changes nothing
    assert db.scalar(select(func.count()).select_from(Order)) == 0
    assert db.scalar(select(Product.stock).where(Product.id == product["id"])) == 10
    assert len(client.get("/cart", headers=user_headers).json()["items"]) == 1


@pytest.mark.parametrize(
    "missing", ["recipient_name", "phone", "address_line1", "city", "state", "postal_code", "country"]
)
def test_checkout_requires_every_address_field(
    client: TestClient, user_headers: dict, checkout_body: dict, missing: str
) -> None:
    del checkout_body["shipping_address"][missing]

    response = client.post("/orders/checkout", json=checkout_body, headers=user_headers)

    assert response.status_code == 422
    assert _error_fields(response) == {missing}


def test_checkout_reports_every_invalid_field_at_once(
    client: TestClient, user_headers: dict, checkout_body: dict
) -> None:
    checkout_body["shipping_address"].update(phone="123", city="", postal_code="abc")

    response = client.post("/orders/checkout", json=checkout_body, headers=user_headers)

    assert _error_fields(response) == {"phone", "city", "postal_code"}


def test_checkout_without_a_body_is_rejected(client: TestClient, user_headers: dict) -> None:
    assert client.post("/orders/checkout", headers=user_headers).status_code == 422
    assert client.post("/orders/checkout", json={"payment_method": "cod"}, headers=user_headers).status_code == 422


def test_postal_code_outside_india_is_not_held_to_the_pin_code_rule(
    client: TestClient, user_headers: dict, create_product: Callable[..., dict], checkout_body: dict
) -> None:
    product = create_product()
    _add(client, user_headers, product["id"])
    checkout_body["shipping_address"].update(
        country="United Kingdom", postal_code="sw1a 1aa", phone="+44 20 7946 0958", state="England"
    )

    response = client.post("/orders/checkout", json=checkout_body, headers=user_headers)

    assert response.status_code == 201
    assert response.json()["shipping_address"]["postal_code"] == "SW1A 1AA"


# --- Payment ----------------------------------------------------------------


def test_cash_on_delivery_order_is_not_marked_paid(
    client: TestClient, user_headers: dict, create_product: Callable[..., dict], checkout_body: dict
) -> None:
    """A successful checkout is an order, not a payment."""
    product = create_product()
    _add(client, user_headers, product["id"])

    order = client.post("/orders/checkout", json=checkout_body, headers=user_headers).json()

    assert order["status"] == "confirmed"
    assert order["payment_method"] == "cod"
    assert order["payment_status"] == "pending"


@pytest.mark.parametrize("method", ["upi", "card", "UPI"])
def test_gateway_payment_methods_are_rejected_as_unavailable(
    client: TestClient,
    db: Session,
    user_headers: dict,
    create_product: Callable[..., dict],
    checkout_body: dict,
    method: str,
) -> None:
    product = create_product()
    _add(client, user_headers, product["id"])
    checkout_body["payment_method"] = method

    response = client.post("/orders/checkout", json=checkout_body, headers=user_headers)

    assert response.status_code == 422
    assert _error_fields(response) == {"payment_method"}
    assert "no payment gateway is integrated" in response.json()["detail"][0]["msg"]
    assert db.scalar(select(func.count()).select_from(Order)) == 0


@pytest.mark.parametrize("method", ["paypal", "", None])
def test_unknown_or_missing_payment_method_is_rejected(
    client: TestClient, user_headers: dict, checkout_body: dict, method: str | None
) -> None:
    checkout_body["payment_method"] = method

    response = client.post("/orders/checkout", json=checkout_body, headers=user_headers)

    assert response.status_code == 422
    assert _error_fields(response) == {"payment_method"}


def test_card_details_are_refused_not_silently_ignored(
    client: TestClient, user_headers: dict, checkout_body: dict
) -> None:
    checkout_body["card_number"] = "4111111111111111"

    response = client.post("/orders/checkout", json=checkout_body, headers=user_headers)

    assert response.status_code == 422
    assert _error_fields(response) == {"card_number"}


# --- Duplicate submission ---------------------------------------------------


def test_double_submitted_checkout_creates_one_order(
    client: TestClient, db: Session, user_headers: dict, create_product: Callable[..., dict], checkout_body: dict
) -> None:
    """The same user sends checkout twice at the same moment (a double click).

    The cart rows are locked, so the second request waits, finds the cart
    empty and gets 400. Without the lock both would create an order.
    """
    product = create_product(stock=10)
    _add(client, user_headers, product["id"], quantity=2)
    barrier = threading.Barrier(2)
    statuses: list[int] = []
    lock = threading.Lock()

    def submit() -> None:
        thread_client = TestClient(app)
        barrier.wait(timeout=10)
        response = thread_client.post("/orders/checkout", json=checkout_body, headers=user_headers)
        with lock:
            statuses.append(response.status_code)

    threads = [threading.Thread(target=submit) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(statuses) == [201, 400]
    assert db.scalar(select(func.count()).select_from(Order)) == 1
    assert db.scalar(select(Product.stock).where(Product.id == product["id"])) == 8  # reduced once
