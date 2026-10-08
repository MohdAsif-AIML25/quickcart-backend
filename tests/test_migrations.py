"""The order-management migration must keep the data that is already there."""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.security import create_access_token
from app.database.session import engine
from tests.conftest import PROJECT_ROOT

PREVIOUS_REVISION = "1a18e1ed71ec"  # the schema before order management


@pytest.fixture
def alembic_config() -> Iterator[Config]:
    config = Config()
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    engine.dispose()  # no idle pooled connection may hold a lock while the schema changes
    yield config
    # Whatever happened in the test, the next test must find the newest schema
    command.upgrade(config, "head")
    engine.dispose()


def test_upgrade_preserves_existing_users_products_and_orders(
    client: TestClient, alembic_config: Config
) -> None:
    command.downgrade(alembic_config, PREVIOUS_REVISION)
    # Rows exactly as the previous version of the application wrote them
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, full_name, role) "
                "VALUES (1, 'old@example.com', 'not-a-real-hash', 'Old Customer', 'user')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO products (id, name, price, stock, category) "
                "VALUES (1, 'Old Mouse', 500.00, 7, 'electronics')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO orders (id, user_id, status, total_amount, created_at) "
                "VALUES (1, 1, 'confirmed', 1000.00, '2026-10-03 09:30:00+00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO order_items (order_id, product_id, product_name, quantity, unit_price) "
                "VALUES (1, 1, 'Old Mouse', 2, 500.00)"
            )
        )
    engine.dispose()

    command.upgrade(alembic_config, "head")

    with engine.connect() as conn:
        user = conn.execute(text("SELECT email, full_name, role FROM users")).one()
        product = conn.execute(text("SELECT name, price, stock FROM products")).one()
        order = conn.execute(text("SELECT * FROM orders")).mappings().one()
        item = conn.execute(text("SELECT product_name, quantity, unit_price FROM order_items")).one()

    assert tuple(user) == ("old@example.com", "Old Customer", "user")
    assert (product.name, str(product.price), product.stock) == ("Old Mouse", "500.00", 7)
    assert (item.product_name, item.quantity, str(item.unit_price)) == ("Old Mouse", 2, "500.00")
    assert (order["status"], str(order["total_amount"])) == ("confirmed", "1000.00")
    assert order["created_at"].isoformat().startswith("2026-10-03")
    # Nothing was invented for the old order: every new column is NULL
    new_columns = [
        "payment_method",
        "payment_status",
        "shipping_recipient_name",
        "shipping_phone",
        "shipping_address_line1",
        "shipping_address_line2",
        "shipping_city",
        "shipping_state",
        "shipping_postal_code",
        "shipping_country",
        "estimated_delivery_date",
        "delivered_at",
        "stock_restored_at",
        "deleted_at",
    ]
    assert {column: order[column] for column in new_columns} == dict.fromkeys(new_columns)

    # ...and the API serves the migrated order
    headers = {"Authorization": f"Bearer {create_access_token(1)}"}
    listed = client.get("/orders/me", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == 1
    assert listed.json()[0]["shipping_address"] is None


def test_database_rejects_an_unknown_order_status() -> None:
    """The CHECK constraint is the last line of defence behind the service code."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, full_name) "
                "VALUES (1, 'a@example.com', 'not-a-real-hash', 'A')"
            )
        )
    with pytest.raises(IntegrityError, match="ck_orders_status_valid"), engine.begin() as conn:
        conn.execute(text("INSERT INTO orders (user_id, status, total_amount) VALUES (1, 'lost', 1.00)"))
