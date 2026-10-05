"""Checkout: the transaction, the rollback, and the concurrent-checkout race."""

import threading
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models import CartItem, Order, Product
from app.services import notification_service


def _add(client: TestClient, headers: dict, product_id: int, quantity: int = 1) -> None:
    response = client.post(
        "/cart/items", json={"product_id": product_id, "quantity": quantity}, headers=headers
    )
    assert response.status_code == 201, response.text


def _stock(db: Session, product_id: int) -> int:
    db.expire_all()  # forget cached objects, read the committed value
    return db.scalar(select(Product.stock).where(Product.id == product_id))


# --- Happy path -------------------------------------------------------------


def test_checkout_creates_order_reduces_stock_and_empties_cart(
    client: TestClient, db: Session, user_headers: dict, create_product: Callable[..., dict]
) -> None:
    mouse = create_product(name="Mouse", price="799.00", stock=10)
    cable = create_product(name="Cable", price="149.50", stock=5)
    _add(client, user_headers, mouse["id"], quantity=2)
    _add(client, user_headers, cable["id"], quantity=1)

    response = client.post("/orders/checkout", headers=user_headers)

    assert response.status_code == 201
    order = response.json()
    assert order["status"] == "confirmed"
    assert order["total_amount"] == "1747.50"  # 2 * 799.00 + 149.50
    assert len(order["items"]) == 2
    assert {item["product_name"] for item in order["items"]} == {"Mouse", "Cable"}
    assert _stock(db, mouse["id"]) == 8
    assert _stock(db, cable["id"]) == 4
    assert client.get("/cart", headers=user_headers).json()["items"] == []


def test_checkout_with_empty_cart_returns_400(client: TestClient, user_headers: dict) -> None:
    response = client.post("/orders/checkout", headers=user_headers)

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "Cart is empty"


def test_checkout_requires_authentication(client: TestClient) -> None:
    assert client.post("/orders/checkout").status_code == 401


# --- Rollback ---------------------------------------------------------------


def test_failed_checkout_rolls_back_everything(
    client: TestClient,
    db: Session,
    admin_headers: dict,
    user_headers: dict,
    create_product: Callable[..., dict],
) -> None:
    """One item is out of stock -> NOTHING changes (atomic: all or nothing)."""
    mouse = create_product(name="Mouse", stock=10)
    cable = create_product(name="Cable", stock=5)
    _add(client, user_headers, mouse["id"], quantity=2)
    _add(client, user_headers, cable["id"], quantity=5)
    # Stock drops after the item was added to the cart
    client.patch(f"/admin/products/{cable['id']}", json={"stock": 1}, headers=admin_headers)

    response = client.post("/orders/checkout", headers=user_headers)

    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["error"]["message"]
    assert _stock(db, mouse["id"]) == 10  # NOT reduced, although the mouse was available
    assert _stock(db, cable["id"]) == 1
    assert db.scalar(select(func.count()).select_from(Order)) == 0
    assert len(client.get("/cart", headers=user_headers).json()["items"]) == 2  # cart intact


def test_checkout_fails_if_product_was_deactivated(
    client: TestClient, admin_headers: dict, user_headers: dict, create_product: Callable[..., dict]
) -> None:
    product = create_product()
    _add(client, user_headers, product["id"])
    client.delete(f"/admin/products/{product['id']}", headers=admin_headers)

    response = client.post("/orders/checkout", headers=user_headers)

    assert response.status_code == 409
    assert "no longer available" in response.json()["error"]["message"]


# --- Name and price snapshot ------------------------------------------------


def test_order_keeps_the_name_and_price_paid_after_the_product_changes(
    client: TestClient, admin_headers: dict, user_headers: dict, create_product: Callable[..., dict]
) -> None:
    """An order is a historical record: it shows what the customer bought, at
    the price they paid, whatever happens to the product afterwards."""
    product = create_product(name="Wireless Mouse", price="799.00")
    _add(client, user_headers, product["id"])
    client.post("/orders/checkout", headers=user_headers)

    client.patch(
        f"/admin/products/{product['id']}",
        json={"name": "Gaming Mouse", "price": "999.00"},
        headers=admin_headers,
    )

    order = client.get("/orders/me", headers=user_headers).json()[0]
    item = order["items"][0]
    assert item["product_name"] == "Wireless Mouse"  # not "Gaming Mouse"
    assert item["unit_price"] == "799.00"  # not "999.00"
    assert order["total_amount"] == "799.00"


# --- Order history ----------------------------------------------------------


def test_users_see_only_their_own_orders(
    client: TestClient, make_user: Callable[..., dict], create_product: Callable[..., dict]
) -> None:
    alice, bob = make_user(), make_user()
    product = create_product()
    _add(client, alice, product["id"])
    client.post("/orders/checkout", headers=alice)

    assert len(client.get("/orders/me", headers=alice).json()) == 1
    assert client.get("/orders/me", headers=bob).json() == []


def test_admin_can_list_all_orders_but_user_cannot(
    client: TestClient,
    admin_headers: dict,
    make_user: Callable[..., dict],
    create_product: Callable[..., dict],
) -> None:
    alice, bob = make_user(), make_user()
    product = create_product()
    for buyer in (alice, bob):
        _add(client, buyer, product["id"])
        client.post("/orders/checkout", headers=buyer)

    admin_view = client.get("/admin/orders", headers=admin_headers)

    assert admin_view.status_code == 200
    assert len(admin_view.json()) == 2
    assert all("user_id" in order for order in admin_view.json())
    assert client.get("/admin/orders", headers=alice).status_code == 403


# --- Side effects -----------------------------------------------------------


def test_checkout_invalidates_the_product_cache(
    client: TestClient, user_headers: dict, create_product: Callable[..., dict]
) -> None:
    product = create_product(stock=10)
    client.get("/products")
    assert client.get("/products").headers["X-Cache"] == "HIT"
    _add(client, user_headers, product["id"], quantity=3)

    client.post("/orders/checkout", headers=user_headers)
    listing = client.get("/products")

    assert listing.headers["X-Cache"] == "MISS"
    assert listing.json()["items"][0]["stock"] == 7  # the new stock, not the cached 10


def test_checkout_schedules_order_confirmation(
    client: TestClient, user_headers: dict, create_product: Callable[..., dict], monkeypatch
) -> None:
    sent: list[tuple] = []
    monkeypatch.setattr(
        notification_service, "send_order_confirmation", lambda *args: sent.append(args)
    )
    product = create_product(price="799.00")
    _add(client, user_headers, product["id"])

    order = client.post("/orders/checkout", headers=user_headers).json()

    assert sent == [(order["id"], "user1@example.com", "799.00")]


def test_confirmation_log_masks_the_email_address() -> None:
    assert notification_service._mask_email("asif@example.com") == "a***@example.com"


# --- Concurrency ------------------------------------------------------------


def _checkout_in_parallel(buyers: list[dict]) -> list[int]:
    """Send one checkout per buyer at the same moment; return the status codes."""
    barrier = threading.Barrier(len(buyers))
    statuses: list[int] = []
    lock = threading.Lock()

    def buy(headers: dict) -> None:
        thread_client = TestClient(app)  # one client per thread
        barrier.wait(timeout=10)  # all threads are released together
        response = thread_client.post("/orders/checkout", headers=headers)
        with lock:
            statuses.append(response.status_code)

    threads = [threading.Thread(target=buy, args=(headers,)) for headers in buyers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return statuses


def test_concurrent_checkouts_never_oversell(
    client: TestClient, db: Session, make_user: Callable[..., dict], create_product: Callable[..., dict]
) -> None:
    """8 buyers race for 3 units: exactly 3 win, 5 get 409, stock ends at 0.

    Without `SELECT ... FOR UPDATE` in order_service.checkout, several threads
    read the same stock value, all pass the check, and the shop oversells.
    """
    stock, buyer_count = 3, 8
    product = create_product(stock=stock)
    buyers = [make_user() for _ in range(buyer_count)]
    for buyer in buyers:
        _add(client, buyer, product["id"])

    statuses = _checkout_in_parallel(buyers)

    assert sorted(statuses) == [201] * stock + [409] * (buyer_count - stock)
    assert _stock(db, product["id"]) == 0  # never negative
    assert db.scalar(select(func.count()).select_from(Order)) == stock
    # The losers keep their carts, because their transactions were rolled back
    assert db.scalar(select(func.count()).select_from(CartItem)) == buyer_count - stock


def test_concurrent_checkouts_of_overlapping_products_do_not_deadlock(
    client: TestClient, db: Session, make_user: Callable[..., dict], create_product: Callable[..., dict]
) -> None:
    """Buyers add the same two products in OPPOSITE order.

    Rows are always locked in product-id order, so nobody waits in a circle.
    """
    first = create_product(name="First", stock=50)
    second = create_product(name="Second", stock=50)
    buyers = [make_user() for _ in range(6)]
    for index, buyer in enumerate(buyers):
        order = (first, second) if index % 2 == 0 else (second, first)
        for product in order:
            _add(client, buyer, product["id"])

    statuses = _checkout_in_parallel(buyers)

    assert statuses == [201] * 6
    assert _stock(db, first["id"]) == 44
    assert _stock(db, second["id"]) == 44
