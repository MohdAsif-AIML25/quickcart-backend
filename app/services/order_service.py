import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models import (
    DELETABLE_ORDER_STATUSES,
    ORDER_STATUS_TRANSITIONS,
    CartItem,
    Order,
    OrderItem,
    OrderStatus,
    PaymentStatus,
    Product,
    User,
)
from app.schemas.order import AdminOrderUpdate, CheckoutRequest
from app.services.cache_service import invalidate_product_cache

logger = logging.getLogger("quickcart.orders")

# An order in one of these statuses is finished: nothing about its delivery can change
FINAL_STATUSES = frozenset({OrderStatus.DELIVERED, OrderStatus.CANCELLED})


def checkout(db: Session, user: User, data: CheckoutRequest) -> Order:
    """Turn the cart into an order in ONE transaction.

    Product rows are locked with SELECT ... FOR UPDATE, so two parallel
    checkouts for the last unit cannot both succeed.
    """
    try:
        # FOR UPDATE on the cart rows too: if the same user submits twice at the
        # same moment, the second request waits here, then finds the cart empty.
        # of=CartItem: lock the cart rows only, not the products joined to them.
        cart_items = db.scalars(
            select(CartItem)
            .where(CartItem.user_id == user.id)
            .order_by(CartItem.id)
            .with_for_update(of=CartItem)
        ).all()
        if not cart_items:
            raise BadRequestError("Cart is empty")

        product_ids = sorted({item.product_id for item in cart_items})
        locked_products = db.scalars(
            select(Product)
            .where(Product.id.in_(product_ids))
            .order_by(Product.id)  # same lock order everywhere -> no deadlocks
            .with_for_update()
            .execution_options(populate_existing=True)  # use the fresh, locked values
        ).all()
        products = {p.id: p for p in locked_products}

        address = data.shipping_address
        order = Order(
            user_id=user.id,
            status=OrderStatus.CONFIRMED.value,
            total_amount=Decimal("0.00"),
            payment_method=data.payment_method.value,
            # Placing an order is not paying for it: nothing here confirms a payment
            payment_status=PaymentStatus.PENDING.value,
            # snapshot: the order keeps the address it was placed with
            shipping_recipient_name=address.recipient_name,
            shipping_phone=address.phone,
            shipping_address_line1=address.address_line1,
            shipping_address_line2=address.address_line2,
            shipping_city=address.city,
            shipping_state=address.state,
            shipping_postal_code=address.postal_code,
            shipping_country=address.country,
        )
        total = Decimal("0.00")

        for item in cart_items:
            product = products.get(item.product_id)
            if product is None or not product.is_active:
                raise ConflictError(f"Product {item.product_id} is no longer available")
            if product.stock < item.quantity:
                raise ConflictError(
                    f"Insufficient stock for '{product.name}': "
                    f"requested {item.quantity}, available {product.stock}"
                )
            product.stock -= item.quantity
            order.items.append(
                OrderItem(
                    product_id=product.id,
                    product_name=product.name,  # snapshot: a later rename must not change this order
                    quantity=item.quantity,
                    unit_price=product.price,  # snapshot: a later price change must not either
                )
            )
            total += product.price * item.quantity

        order.total_amount = total
        db.add(order)
        db.execute(delete(CartItem).where(CartItem.user_id == user.id))
        db.commit()  # everything above becomes visible at once, or not at all
    except Exception:
        db.rollback()  # stock, order, and cart all return to their original state
        raise

    db.refresh(order)
    invalidate_product_cache()  # stock changed -> cached product listings are stale
    logger.info("order_created", extra={"order_id": order.id, "user_id": user.id})
    return order


def list_user_orders(db: Session, user: User) -> list[Order]:
    return list(
        db.scalars(
            select(Order)
            .where(Order.user_id == user.id, Order.deleted_at.is_(None))
            .order_by(Order.id.desc())
        ).all()
    )


def get_user_order(db: Session, user: User, order_id: int) -> Order:
    # Filter by user_id too: another user's order looks "not found", not "forbidden"
    order = db.scalar(
        select(Order).where(
            Order.id == order_id, Order.user_id == user.id, Order.deleted_at.is_(None)
        )
    )
    if order is None:
        raise NotFoundError("Order not found")
    return order


def list_all_orders(db: Session, *, page: int, limit: int) -> list[Order]:
    return list(
        db.scalars(
            select(Order)
            .where(Order.deleted_at.is_(None))
            .order_by(Order.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        ).all()
    )


def _lock_order(db: Session, order_id: int) -> Order:
    """Read one order and hold its row lock until the transaction ends.

    Every admin change to an order starts here, so two requests for the same
    order run one after the other. The second one sees what the first one wrote.
    """
    order = db.scalar(
        select(Order)
        .where(Order.id == order_id, Order.deleted_at.is_(None))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if order is None:
        raise NotFoundError("Order not found")
    return order


def _restore_stock_once(db: Session, order: Order) -> bool:
    """Give the order's units back to the products, at most once per order.

    The ONLY place that returns stock. Cancellation and deletion both call it.
    The caller must hold the order's row lock (see _lock_order): the lock makes
    "check stock_restored_at, then set it" safe against a parallel request.
    """
    if order.stock_restored_at is not None:
        return False

    quantities: dict[int, int] = {}
    for item in order.items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity

    products = db.scalars(
        select(Product)
        .where(Product.id.in_(sorted(quantities)))
        .order_by(Product.id)  # the same lock order as checkout -> no deadlocks
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    for product in products:
        product.stock += quantities[product.id]

    order.stock_restored_at = datetime.now(UTC)
    return True


def update_order(db: Session, order_id: int, data: AdminOrderUpdate) -> Order:
    """Admin: move the order to its next status and/or set the estimated delivery date."""
    stock_restored = False
    try:
        order = _lock_order(db, order_id)
        previous_status = OrderStatus(order.status)

        if "status" in data.model_fields_set:
            new_status = data.status
            if new_status not in ORDER_STATUS_TRANSITIONS[previous_status]:
                raise ConflictError(
                    f"Cannot change order status from '{previous_status}' to '{new_status}'"
                )
            order.status = new_status.value
            if new_status is OrderStatus.DELIVERED:
                order.delivered_at = datetime.now(UTC)
            elif new_status is OrderStatus.CANCELLED:
                stock_restored = _restore_stock_once(db, order)
                order.estimated_delivery_date = None  # nothing will be delivered

        if "estimated_delivery_date" in data.model_fields_set:
            current_status = OrderStatus(order.status)
            if current_status in FINAL_STATUSES:
                raise ConflictError(
                    f"Cannot change the estimated delivery date of a {current_status} order"
                )
            new_date = data.estimated_delivery_date
            if new_date is not None and new_date < order.created_at.astimezone(UTC).date():
                raise BadRequestError(
                    "Estimated delivery date cannot be earlier than the date the order was placed"
                )
            order.estimated_delivery_date = new_date

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(order)
    if stock_restored:
        invalidate_product_cache()
    logger.info(
        "order_updated",
        extra={"order_id": order.id, "from_status": previous_status.value, "status": order.status},
    )
    return order


def delete_order(db: Session, order_id: int, admin: User) -> None:
    """Admin: soft-delete a confirmed order and give its stock back.

    The row is kept (deleted_at is set), so the record survives for audits.
    A repeated or parallel request finds deleted_at already set and gets a 404:
    the stock is restored exactly once.
    """
    try:
        order = _lock_order(db, order_id)
        status = OrderStatus(order.status)
        if status not in DELETABLE_ORDER_STATUSES:
            raise ConflictError(
                f"Only confirmed orders that have not shipped can be deleted; this order is {status}"
            )
        stock_restored = _restore_stock_once(db, order)
        order.deleted_at = datetime.now(UTC)
        db.commit()
    except Exception:
        db.rollback()
        raise

    if stock_restored:
        invalidate_product_cache()
    logger.info("order_deleted", extra={"order_id": order_id, "admin_id": admin.id})
