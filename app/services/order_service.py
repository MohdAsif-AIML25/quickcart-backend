import logging
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, ConflictError
from app.models import CartItem, Order, OrderItem, Product, User

logger = logging.getLogger("quickcart.orders")


def checkout(db: Session, user: User) -> Order:
    """Turn the cart into an order in ONE transaction.

    Product rows are locked with SELECT ... FOR UPDATE, so two parallel
    checkouts for the last unit cannot both succeed.
    """
    try:
        cart_items = db.scalars(select(CartItem).where(CartItem.user_id == user.id)).all()
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

        order = Order(user_id=user.id, status="confirmed", total_amount=Decimal("0.00"))
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
                OrderItem(product_id=product.id, quantity=item.quantity, unit_price=product.price)
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
    logger.info("order_created", extra={"order_id": order.id, "user_id": user.id})
    return order


def list_user_orders(db: Session, user: User) -> list[Order]:
    return list(
        db.scalars(select(Order).where(Order.user_id == user.id).order_by(Order.id.desc())).all()
    )


def list_all_orders(db: Session, *, page: int, limit: int) -> list[Order]:
    return list(
        db.scalars(
            select(Order).order_by(Order.id.desc()).offset((page - 1) * limit).limit(limit)
        ).all()
    )