from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class OrderStatus(StrEnum):
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class PaymentMethod(StrEnum):
    COD = "cod"  # Cash on Delivery: the only method until a payment gateway is integrated


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"  # never set by checkout; reserved for a real payment confirmation


# The order life cycle. A status that is not listed as a target cannot be reached:
# an order never moves backwards, and "delivered" and "cancelled" are final.
# Cancelling is possible only while the goods are still in the warehouse.
ORDER_STATUS_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.CONFIRMED: frozenset({OrderStatus.PROCESSING, OrderStatus.CANCELLED}),
    OrderStatus.PROCESSING: frozenset({OrderStatus.SHIPPED, OrderStatus.CANCELLED}),
    OrderStatus.SHIPPED: frozenset({OrderStatus.DELIVERED}),
    OrderStatus.DELIVERED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
}

# Only an order nobody has started working on may be deleted by an admin
DELETABLE_ORDER_STATUSES = frozenset({OrderStatus.CONFIRMED})


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('confirmed', 'processing', 'shipped', 'delivered', 'cancelled')",
            name="status_valid",
        ),
        CheckConstraint("payment_method IN ('cod')", name="payment_method_valid"),
        CheckConstraint("payment_status IN ('pending', 'paid')", name="payment_status_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=OrderStatus.CONFIRMED.value)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    # Payment. NULL = an order placed before payment information was recorded.
    # payment_status is independent from `status`: a delivered order can be unpaid.
    payment_method: Mapped[str | None] = mapped_column(String(20))
    payment_status: Mapped[str | None] = mapped_column(String(20))

    # Delivery address snapshot: copied at checkout, never changed afterwards.
    # All NULL = an order placed before addresses were collected.
    shipping_recipient_name: Mapped[str | None] = mapped_column(String(100))
    shipping_phone: Mapped[str | None] = mapped_column(String(20))
    shipping_address_line1: Mapped[str | None] = mapped_column(String(200))
    shipping_address_line2: Mapped[str | None] = mapped_column(String(200))
    shipping_city: Mapped[str | None] = mapped_column(String(100))
    shipping_state: Mapped[str | None] = mapped_column(String(100))
    shipping_postal_code: Mapped[str | None] = mapped_column(String(12))
    shipping_country: Mapped[str | None] = mapped_column(String(60))

    estimated_delivery_date: Mapped[date | None] = mapped_column(Date)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Set once, when a cancellation or deletion gives the stock back.
    # It is the guard that makes stock restoration happen at most once per order.
    stock_restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Soft delete: the row stays, but the order disappears from every listing.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def shipping_address(self) -> dict[str, str | None] | None:
        """The address as one object, or None for an order that has none."""
        if self.shipping_recipient_name is None:
            return None
        return {
            "recipient_name": self.shipping_recipient_name,
            "phone": self.shipping_phone,
            "address_line1": self.shipping_address_line1,
            "address_line2": self.shipping_address_line2,
            "city": self.shipping_city,
            "state": self.shipping_state,
            "country": self.shipping_country,
            "postal_code": self.shipping_postal_code,
        }


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    product_name: Mapped[str] = mapped_column(String(200))  # name snapshot
    quantity: Mapped[int]
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # price snapshot

    order: Mapped[Order] = relationship(back_populates="items")
