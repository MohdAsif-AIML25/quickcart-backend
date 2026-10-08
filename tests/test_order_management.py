"""Order management: ownership, admin-only operations, the status life cycle,
soft delete, and exactly-once stock restoration."""

import threading
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models import Order, OrderItem, Product, User

PlaceOrder = Callable[..., dict]
CreateProduct = Callable[..., dict]


def _stock(db: Session, product_id: int) -> int:
    db.expire_all()  # forget cached objects, read the committed value
    return db.scalar(select(Product.stock).where(Product.id == product_id))


def _set_status(client: TestClient, admin_headers: dict, order_id: int, status: str):
    return client.patch(f"/admin/orders/{order_id}", json={"status": status}, headers=admin_headers)


def _advance(client: TestClient, admin_headers: dict, order_id: int, *statuses: str) -> None:
    for status in statuses:
        response = _set_status(client, admin_headers, order_id, status)
        assert response.status_code == 200, response.text


def _in_parallel(count: int, send: Callable[[TestClient], int]) -> list[int]:
    """Run `send` in `count` threads at the same moment; return the status codes."""
    barrier = threading.Barrier(count)
    statuses: list[int] = []
    lock = threading.Lock()

    def worker() -> None:
        thread_client = TestClient(app)  # one client per thread
        barrier.wait(timeout=10)
        status = send(thread_client)
        with lock:
            statuses.append(status)

    threads = [threading.Thread(target=worker) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return statuses


# --- Ownership --------------------------------------------------------------


def test_customer_can_read_own_order_but_not_another_users(
    client: TestClient, make_user: Callable[..., dict], create_product: CreateProduct, place_order: PlaceOrder
) -> None:
    alice, bob = make_user(), make_user()
    order = place_order(alice, create_product()["id"])

    own = client.get(f"/orders/{order['id']}", headers=alice)
    other = client.get(f"/orders/{order['id']}", headers=bob)

    assert own.status_code == 200
    assert own.json()["id"] == order["id"]
    assert "user_id" not in own.json()
    # 404 (not 403) does not reveal that the order exists
    assert other.status_code == 404
    assert other.json()["error"]["code"] == "not_found"


def test_order_endpoints_require_authentication(client: TestClient) -> None:
    assert client.get("/orders/me").status_code == 401
    assert client.get("/orders/1").status_code == 401
    assert client.get("/admin/orders").status_code == 401
    assert client.patch("/admin/orders/1", json={"status": "processing"}).status_code == 401
    assert client.delete("/admin/orders/1").status_code == 401


def test_get_unknown_order_returns_404(client: TestClient, user_headers: dict) -> None:
    assert client.get("/orders/9999", headers=user_headers).status_code == 404


# --- Admin-only operations --------------------------------------------------


def test_customer_cannot_change_status_or_delivery_date(
    client: TestClient, db: Session, user_headers: dict, create_product: CreateProduct, place_order: PlaceOrder
) -> None:
    order = place_order(user_headers, create_product()["id"])

    status = client.patch(f"/admin/orders/{order['id']}", json={"status": "cancelled"}, headers=user_headers)
    eta = client.patch(
        f"/admin/orders/{order['id']}", json={"estimated_delivery_date": "2030-01-01"}, headers=user_headers
    )

    assert status.status_code == eta.status_code == 403
    assert status.json()["error"]["code"] == "forbidden"
    saved = db.get(Order, order["id"])
    assert saved.status == "confirmed"
    assert saved.estimated_delivery_date is None


def test_customer_cannot_delete_an_order(
    client: TestClient, db: Session, user_headers: dict, create_product: CreateProduct, place_order: PlaceOrder
) -> None:
    product = create_product(stock=10)
    order = place_order(user_headers, product["id"], quantity=3)

    response = client.delete(f"/admin/orders/{order['id']}", headers=user_headers)

    assert response.status_code == 403
    assert db.get(Order, order["id"]).deleted_at is None
    assert _stock(db, product["id"]) == 7  # nothing was given back
    assert len(client.get("/orders/me", headers=user_headers).json()) == 1


def test_customer_order_routes_offer_no_way_to_delete_or_modify(
    client: TestClient, user_headers: dict, create_product: CreateProduct, place_order: PlaceOrder
) -> None:
    """There is simply no customer endpoint for it: the method is not allowed."""
    order = place_order(user_headers, create_product()["id"])

    assert client.delete(f"/orders/{order['id']}", headers=user_headers).status_code == 405
    assert client.patch(f"/orders/{order['id']}", json={"status": "cancelled"}, headers=user_headers).status_code == 405


def test_customer_can_still_remove_cart_items_before_checkout(
    client: TestClient, user_headers: dict, create_product: CreateProduct
) -> None:
    product = create_product()
    item = client.post("/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=user_headers).json()

    assert client.delete(f"/cart/items/{item['id']}", headers=user_headers).status_code == 204
    assert client.get("/cart", headers=user_headers).json()["items"] == []


# --- Admin view -------------------------------------------------------------


def test_admin_list_shows_details_and_what_can_be_done_next(
    client: TestClient, admin_headers: dict, user_headers: dict, create_product: CreateProduct, place_order: PlaceOrder
) -> None:
    order = place_order(user_headers, create_product()["id"])

    listed = client.get("/admin/orders", headers=admin_headers).json()[0]

    assert listed["id"] == order["id"]
    assert listed["shipping_address"]["city"] == "Bengaluru"
    assert listed["payment_method"] == "cod"
    assert listed["payment_status"] == "pending"
    assert listed["allowed_next_statuses"] == ["processing", "cancelled"]
    assert listed["can_delete"] is True


# --- Status life cycle ------------------------------------------------------


def test_order_moves_through_the_full_life_cycle(
    client: TestClient, admin_headers: dict, user_headers: dict, create_product: CreateProduct, place_order: PlaceOrder
) -> None:
    order = place_order(user_headers, create_product()["id"])
    before = datetime.now(UTC) - timedelta(seconds=5)

    for status in ("processing", "shipped"):
        updated = _set_status(client, admin_headers, order["id"], status).json()
        assert updated["status"] == status
        assert updated["delivered_at"] is None
    delivered = _set_status(client, admin_headers, order["id"], "delivered").json()

    assert delivered["status"] == "delivered"
    assert delivered["allowed_next_statuses"] == []
    assert delivered["can_delete"] is False
    delivered_at = datetime.fromisoformat(delivered["delivered_at"])
    assert before <= delivered_at <= datetime.now(UTC) + timedelta(seconds=5)
    # The customer sees the same status and delivery time
    mine = client.get(f"/orders/{order['id']}", headers=user_headers).json()
    assert mine["status"] == "delivered"
    assert mine["delivered_at"] == delivered["delivered_at"]


@pytest.mark.parametrize(
    ("path", "target"),
    [
        ((), "confirmed"),  # same status
        ((), "shipped"),  # skips processing
        ((), "delivered"),
        (("processing",), "confirmed"),  # backwards
        (("processing",), "delivered"),
        (("processing", "shipped"), "processing"),
        (("processing", "shipped"), "cancelled"),  # the goods have left
        (("processing", "shipped", "delivered"), "shipped"),
        (("processing", "shipped", "delivered"), "cancelled"),
        (("cancelled",), "confirmed"),
        (("cancelled",), "processing"),
        (("cancelled",), "cancelled"),
    ],
)
def test_invalid_status_transitions_are_rejected(
    client: TestClient,
    db: Session,
    admin_headers: dict,
    user_headers: dict,
    create_product: CreateProduct,
    place_order: PlaceOrder,
    path: tuple[str, ...],
    target: str,
) -> None:
    order = place_order(user_headers, create_product()["id"])
    _advance(client, admin_headers, order["id"], *path)
    current = path[-1] if path else "confirmed"

    response = _set_status(client, admin_headers, order["id"], target)

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "conflict",
        "message": f"Cannot change order status from '{current}' to '{target}'",
    }
    db.expire_all()
    assert db.get(Order, order["id"]).status == current


def test_unknown_status_and_empty_update_are_validation_errors(
    client: TestClient, admin_headers: dict, user_headers: dict, create_product: CreateProduct, place_order: PlaceOrder
) -> None:
    order = place_order(user_headers, create_product()["id"])
    url = f"/admin/orders/{order['id']}"

    assert client.patch(url, json={"status": "refunded"}, headers=admin_headers).status_code == 422
    assert client.patch(url, json={"status": None}, headers=admin_headers).status_code == 422
    assert client.patch(url, json={}, headers=admin_headers).status_code == 422
    # payment_status is not something this endpoint can touch
    assert client.patch(url, json={"payment_status": "paid"}, headers=admin_headers).status_code == 422


def test_update_unknown_order_returns_404(client: TestClient, admin_headers: dict) -> None:
    assert _set_status(client, admin_headers, 9999, "processing").status_code == 404


def test_payment_status_is_independent_from_order_status(
    client: TestClient, admin_headers: dict, user_headers: dict, create_product: CreateProduct, place_order: PlaceOrder
) -> None:
    """Delivering an order does not pay for it, and cancelling does not refund it."""
    delivered = place_order(user_headers, create_product(name="A")["id"])
    cancelled = place_order(user_headers, create_product(name="B")["id"])

    _advance(client, admin_headers, delivered["id"], "processing", "shipped", "delivered")
    _advance(client, admin_headers, cancelled["id"], "cancelled")

    for order_id in (delivered["id"], cancelled["id"]):
        order = client.get(f"/orders/{order_id}", headers=user_headers).json()
        assert order["payment_method"] == "cod"
        assert order["payment_status"] == "pending"


# --- Estimated delivery date ------------------------------------------------


def test_admin_sets_and_clears_the_estimated_delivery_date(
    client: TestClient, admin_headers: dict, user_headers: dict, create_product: CreateProduct, place_order: PlaceOrder
) -> None:
    order = place_order(user_headers, create_product()["id"])
    assert order["estimated_delivery_date"] is None  # the UI shows "Not scheduled"
    eta = (date.today() + timedelta(days=5)).isoformat()
    url = f"/admin/orders/{order['id']}"

    scheduled = client.patch(url, json={"estimated_delivery_date": eta}, headers=admin_headers)

    assert scheduled.status_code == 200
    assert scheduled.json()["estimated_delivery_date"] == eta
    assert scheduled.json()["status"] == "confirmed"  # the status was not sent, so it did not change
    assert client.get(f"/orders/{order['id']}", headers=user_headers).json()["estimated_delivery_date"] == eta

    cleared = client.patch(url, json={"estimated_delivery_date": None}, headers=admin_headers)

    assert cleared.status_code == 200
    assert cleared.json()["estimated_delivery_date"] is None


def test_status_and_delivery_date_can_change_in_one_request(
    client: TestClient, admin_headers: dict, user_headers: dict, create_product: CreateProduct, place_order: PlaceOrder
) -> None:
    order = place_order(user_headers, create_product()["id"])
    eta = (date.today() + timedelta(days=3)).isoformat()

    response = client.patch(
        f"/admin/orders/{order['id']}",
        json={"status": "processing", "estimated_delivery_date": eta},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "processing"
    assert response.json()["estimated_delivery_date"] == eta


def test_estimated_delivery_date_cannot_be_before_the_order_date(
    client: TestClient, admin_headers: dict, user_headers: dict, create_product: CreateProduct, place_order: PlaceOrder
) -> None:
    order = place_order(user_headers, create_product()["id"])
    url = f"/admin/orders/{order['id']}"

    past = client.patch(url, json={"estimated_delivery_date": "2020-01-01"}, headers=admin_headers)
    invalid = client.patch(url, json={"estimated_delivery_date": "not-a-date"}, headers=admin_headers)

    assert past.status_code == 400
    assert past.json()["error"]["code"] == "bad_request"
    assert invalid.status_code == 422


def test_rejected_update_changes_nothing(
    client: TestClient,
    db: Session,
    admin_headers: dict,
    user_headers: dict,
    create_product: CreateProduct,
    place_order: PlaceOrder,
) -> None:
    """A valid status together with an invalid date: the whole request is rolled back."""
    order = place_order(user_headers, create_product()["id"])

    response = client.patch(
        f"/admin/orders/{order['id']}",
        json={"status": "processing", "estimated_delivery_date": "2020-01-01"},
        headers=admin_headers,
    )

    assert response.status_code == 400
    db.expire_all()
    assert db.get(Order, order["id"]).status == "confirmed"


def test_delivery_date_of_a_finished_order_cannot_change(
    client: TestClient, admin_headers: dict, user_headers: dict, create_product: CreateProduct, place_order: PlaceOrder
) -> None:
    delivered = place_order(user_headers, create_product(name="A")["id"])
    cancelled = place_order(user_headers, create_product(name="B")["id"])
    _advance(client, admin_headers, delivered["id"], "processing", "shipped", "delivered")
    _advance(client, admin_headers, cancelled["id"], "cancelled")
    eta = (date.today() + timedelta(days=2)).isoformat()

    for order_id in (delivered["id"], cancelled["id"]):
        response = client.patch(
            f"/admin/orders/{order_id}", json={"estimated_delivery_date": eta}, headers=admin_headers
        )
        assert response.status_code == 409


# --- Cancellation -----------------------------------------------------------


def test_cancelling_restores_stock_and_clears_the_delivery_date(
    client: TestClient,
    db: Session,
    admin_headers: dict,
    user_headers: dict,
    create_product: CreateProduct,
    place_order: PlaceOrder,
) -> None:
    product = create_product(stock=10)
    order = place_order(user_headers, product["id"], quantity=4)
    eta = (date.today() + timedelta(days=5)).isoformat()
    client.patch(
        f"/admin/orders/{order['id']}",
        json={"status": "processing", "estimated_delivery_date": eta},
        headers=admin_headers,
    )
    assert _stock(db, product["id"]) == 6

    cancelled = _set_status(client, admin_headers, order["id"], "cancelled")

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["estimated_delivery_date"] is None
    assert _stock(db, product["id"]) == 10
    # The customer still sees the cancelled order: cancelling is not deleting
    assert client.get("/orders/me", headers=user_headers).json()[0]["status"] == "cancelled"


def test_repeated_cancellation_restores_stock_only_once(
    client: TestClient,
    db: Session,
    admin_headers: dict,
    user_headers: dict,
    create_product: CreateProduct,
    place_order: PlaceOrder,
) -> None:
    product = create_product(stock=10)
    order = place_order(user_headers, product["id"], quantity=4)

    statuses = [_set_status(client, admin_headers, order["id"], "cancelled").status_code for _ in range(3)]

    assert statuses == [200, 409, 409]
    assert _stock(db, product["id"]) == 10  # not 14 or 18


def test_cancelled_order_cannot_be_deleted_for_a_second_restoration(
    client: TestClient,
    db: Session,
    admin_headers: dict,
    user_headers: dict,
    create_product: CreateProduct,
    place_order: PlaceOrder,
) -> None:
    product = create_product(stock=10)
    order = place_order(user_headers, product["id"], quantity=4)
    _advance(client, admin_headers, order["id"], "cancelled")

    response = client.delete(f"/admin/orders/{order['id']}", headers=admin_headers)

    assert response.status_code == 409
    assert _stock(db, product["id"]) == 10


def test_concurrent_cancellations_restore_stock_exactly_once(
    client: TestClient,
    db: Session,
    admin_headers: dict,
    user_headers: dict,
    create_product: CreateProduct,
    place_order: PlaceOrder,
) -> None:
    product = create_product(stock=10)
    order = place_order(user_headers, product["id"], quantity=4)

    statuses = _in_parallel(
        6,
        lambda c: c.patch(
            f"/admin/orders/{order['id']}", json={"status": "cancelled"}, headers=admin_headers
        ).status_code,
    )

    assert sorted(statuses) == [200] + [409] * 5
    assert _stock(db, product["id"]) == 10


# --- Deletion ---------------------------------------------------------------


def test_admin_delete_hides_the_order_but_keeps_the_row(
    client: TestClient,
    db: Session,
    admin_headers: dict,
    user_headers: dict,
    create_product: CreateProduct,
    place_order: PlaceOrder,
) -> None:
    product = create_product(stock=10)
    kept = place_order(user_headers, product["id"], quantity=1)
    deleted = place_order(user_headers, product["id"], quantity=3)

    response = client.delete(f"/admin/orders/{deleted['id']}", headers=admin_headers)

    assert response.status_code == 204
    # Hidden from every listing and from the detail endpoint...
    assert [o["id"] for o in client.get("/orders/me", headers=user_headers).json()] == [kept["id"]]
    assert [o["id"] for o in client.get("/admin/orders", headers=admin_headers).json()] == [kept["id"]]
    assert client.get(f"/orders/{deleted['id']}", headers=user_headers).status_code == 404
    # ...but the record and its lines are still in the database
    db.expire_all()
    row = db.get(Order, deleted["id"])
    assert row is not None
    assert row.deleted_at is not None
    assert row.status == "confirmed"
    assert row.total_amount == Decimal(deleted["total_amount"])
    assert len(row.items) == 1
    assert _stock(db, product["id"]) == 9  # 10 - 1 (kept) - 3 + 3 (given back)


def test_repeated_delete_restores_stock_only_once(
    client: TestClient,
    db: Session,
    admin_headers: dict,
    user_headers: dict,
    create_product: CreateProduct,
    place_order: PlaceOrder,
) -> None:
    product = create_product(stock=10)
    order = place_order(user_headers, product["id"], quantity=4)
    url = f"/admin/orders/{order['id']}"

    statuses = [client.delete(url, headers=admin_headers).status_code for _ in range(3)]

    assert statuses == [204, 404, 404]
    assert _stock(db, product["id"]) == 10  # not 14 or 18


def test_concurrent_deletes_restore_stock_exactly_once(
    client: TestClient,
    db: Session,
    admin_headers: dict,
    user_headers: dict,
    create_product: CreateProduct,
    place_order: PlaceOrder,
) -> None:
    """Six delete requests arrive together: one wins, five find the order gone.

    Without the row lock in order_service._lock_order, several requests read
    stock_restored_at = NULL and each adds the units back.
    """
    product = create_product(stock=10)
    order = place_order(user_headers, product["id"], quantity=4)

    statuses = _in_parallel(
        6, lambda c: c.delete(f"/admin/orders/{order['id']}", headers=admin_headers).status_code
    )

    assert sorted(statuses) == [204] + [404] * 5
    assert _stock(db, product["id"]) == 10


def test_delete_racing_with_cancel_restores_stock_exactly_once(
    client: TestClient,
    db: Session,
    admin_headers: dict,
    user_headers: dict,
    create_product: CreateProduct,
    place_order: PlaceOrder,
) -> None:
    """Deletion and cancellation share one restore function and one lock."""
    product = create_product(stock=10)
    order = place_order(user_headers, product["id"], quantity=4)
    url = f"/admin/orders/{order['id']}"
    calls = iter(["delete", "cancel"] * 3)
    calls_lock = threading.Lock()

    def send(thread_client: TestClient) -> int:
        with calls_lock:
            action = next(calls)
        if action == "delete":
            return thread_client.delete(url, headers=admin_headers).status_code
        return thread_client.patch(url, json={"status": "cancelled"}, headers=admin_headers).status_code

    statuses = _in_parallel(6, send)

    assert sum(status in (200, 204) for status in statuses) == 1  # exactly one request won
    assert _stock(db, product["id"]) == 10


@pytest.mark.parametrize(
    "path", [("processing",), ("processing", "shipped"), ("processing", "shipped", "delivered")]
)
def test_only_confirmed_orders_can_be_deleted(
    client: TestClient,
    db: Session,
    admin_headers: dict,
    user_headers: dict,
    create_product: CreateProduct,
    place_order: PlaceOrder,
    path: tuple[str, ...],
) -> None:
    product = create_product(stock=10)
    order = place_order(user_headers, product["id"], quantity=4)
    _advance(client, admin_headers, order["id"], *path)

    response = client.delete(f"/admin/orders/{order['id']}", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    db.expire_all()
    assert db.get(Order, order["id"]).deleted_at is None
    assert _stock(db, product["id"]) == 6
    assert len(client.get("/orders/me", headers=user_headers).json()) == 1


def test_delete_unknown_order_returns_404(client: TestClient, admin_headers: dict) -> None:
    assert client.delete("/admin/orders/9999", headers=admin_headers).status_code == 404


def test_deleted_order_cannot_be_updated(
    client: TestClient, admin_headers: dict, user_headers: dict, create_product: CreateProduct, place_order: PlaceOrder
) -> None:
    order = place_order(user_headers, create_product()["id"])
    client.delete(f"/admin/orders/{order['id']}", headers=admin_headers)

    assert _set_status(client, admin_headers, order["id"], "processing").status_code == 404


def test_delete_restores_every_line_of_a_multi_product_order(
    client: TestClient,
    db: Session,
    admin_headers: dict,
    user_headers: dict,
    create_product: CreateProduct,
    checkout_body: dict,
) -> None:
    mouse = create_product(name="Mouse", stock=10)
    cable = create_product(name="Cable", stock=5)
    for product, quantity in ((mouse, 2), (cable, 5)):
        client.post("/cart/items", json={"product_id": product["id"], "quantity": quantity}, headers=user_headers)
    order = client.post("/orders/checkout", json=checkout_body, headers=user_headers).json()
    # A product removed from the catalogue after the sale still gets its units back
    client.delete(f"/admin/products/{cable['id']}", headers=admin_headers)

    assert client.delete(f"/admin/orders/{order['id']}", headers=admin_headers).status_code == 204

    assert _stock(db, mouse["id"]) == 10
    assert _stock(db, cable["id"]) == 5


def test_delete_and_cancel_invalidate_the_product_cache(
    client: TestClient, admin_headers: dict, user_headers: dict, create_product: CreateProduct, place_order: PlaceOrder
) -> None:
    product = create_product(stock=10)
    to_delete = place_order(user_headers, product["id"], quantity=3)
    to_cancel = place_order(user_headers, product["id"], quantity=2)
    client.get("/products")
    assert client.get("/products").headers["X-Cache"] == "HIT"

    client.delete(f"/admin/orders/{to_delete['id']}", headers=admin_headers)
    after_delete = client.get("/products")

    assert after_delete.headers["X-Cache"] == "MISS"
    assert after_delete.json()["items"][0]["stock"] == 8  # the restored stock, not the cached 5
    assert client.get("/products").headers["X-Cache"] == "HIT"

    _set_status(client, admin_headers, to_cancel["id"], "cancelled")
    after_cancel = client.get("/products")

    assert after_cancel.headers["X-Cache"] == "MISS"
    assert after_cancel.json()["items"][0]["stock"] == 10


# --- Orders placed before addresses and payment existed ---------------------


@pytest.fixture
def legacy_order(db: Session, user_headers: dict, create_product: CreateProduct) -> dict:
    """An order as the previous version of the app wrote it: no address, no payment."""
    product = create_product(name="Old Mouse", price="500.00", stock=7)
    user = db.scalar(select(User).where(User.role == "user"))
    order = Order(user_id=user.id, status="confirmed", total_amount=Decimal("1000.00"))
    order.items.append(
        OrderItem(product_id=product["id"], product_name="Old Mouse", quantity=2, unit_price=Decimal("500.00"))
    )
    db.add(order)
    db.commit()
    return {"id": order.id, "product_id": product["id"]}


def test_legacy_order_is_shown_without_invented_values(
    client: TestClient, admin_headers: dict, user_headers: dict, legacy_order: dict
) -> None:
    mine = client.get("/orders/me", headers=user_headers)
    detail = client.get(f"/orders/{legacy_order['id']}", headers=user_headers)
    admin_view = client.get("/admin/orders", headers=admin_headers)

    assert mine.status_code == detail.status_code == admin_view.status_code == 200
    for order in (mine.json()[0], detail.json(), admin_view.json()[0]):
        assert order["status"] == "confirmed"
        assert order["total_amount"] == "1000.00"
        assert order["items"][0]["product_name"] == "Old Mouse"
        # Unknown stays unknown: no made-up address, method or "paid"
        assert order["shipping_address"] is None
        assert order["payment_method"] is None
        assert order["payment_status"] is None
        assert order["estimated_delivery_date"] is None
        assert order["delivered_at"] is None


def test_legacy_order_can_be_managed_like_any_other(
    client: TestClient, db: Session, admin_headers: dict, user_headers: dict, legacy_order: dict
) -> None:
    eta = (date.today() + timedelta(days=4)).isoformat()

    updated = client.patch(
        f"/admin/orders/{legacy_order['id']}",
        json={"status": "processing", "estimated_delivery_date": eta},
        headers=admin_headers,
    )

    assert updated.status_code == 200
    assert updated.json()["estimated_delivery_date"] == eta
    assert updated.json()["payment_status"] is None  # still not invented

    cancelled = _set_status(client, admin_headers, legacy_order["id"], "cancelled")

    assert cancelled.status_code == 200
    assert _stock(db, legacy_order["product_id"]) == 9  # 7 + the 2 units of the order


def test_legacy_order_can_be_deleted_with_stock_restored_once(
    client: TestClient, db: Session, admin_headers: dict, legacy_order: dict
) -> None:
    url = f"/admin/orders/{legacy_order['id']}"

    assert client.delete(url, headers=admin_headers).status_code == 204
    assert client.delete(url, headers=admin_headers).status_code == 404
    assert _stock(db, legacy_order["product_id"]) == 9
