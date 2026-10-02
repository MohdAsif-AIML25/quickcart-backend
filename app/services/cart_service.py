from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models import CartItem, User
from app.schemas.cart import MAX_QUANTITY_PER_ITEM, CartItemAdd, CartItemRead, CartRead
from app.services.product_service import get_product_or_404


def _to_read(item: CartItem) -> CartItemRead:
    return CartItemRead(
        id=item.id,
        product_id=item.product_id,
        product_name=item.product.name,
        unit_price=item.product.price,
        quantity=item.quantity,
        subtotal=item.product.price * item.quantity,
    )


def add_item(db: Session, user: User, data: CartItemAdd) -> CartItemRead:
    product = get_product_or_404(db, data.product_id, active_only=True)
    item = db.scalar(
        select(CartItem).where(CartItem.user_id == user.id, CartItem.product_id == product.id)
    )
    new_quantity = data.quantity + (item.quantity if item else 0)

    if new_quantity > MAX_QUANTITY_PER_ITEM:
        raise BadRequestError(f"Maximum {MAX_QUANTITY_PER_ITEM} units per product")
    if new_quantity > product.stock:
        raise ConflictError(f"Only {product.stock} unit(s) of '{product.name}' available")

    if item:
        item.quantity = new_quantity  # same product again -> increase quantity
    else:
        item = CartItem(user_id=user.id, product_id=product.id, quantity=new_quantity)
        db.add(item)

    try:
        db.commit()
    except IntegrityError as exc:  # unique(user_id, product_id) hit by a parallel request
        db.rollback()
        raise ConflictError("Cart was modified at the same time, please retry") from exc
    db.refresh(item)
    return _to_read(item)


def get_cart(db: Session, user: User) -> CartRead:
    items = db.scalars(
        select(CartItem).where(CartItem.user_id == user.id).order_by(CartItem.id)
    ).all()
    lines = [_to_read(i) for i in items]
    return CartRead(
        items=lines,
        total_items=sum(line.quantity for line in lines),
        total_amount=sum((line.subtotal for line in lines), Decimal("0.00")),
    )


def remove_item(db: Session, user: User, item_id: int) -> None:
    # Filter by user_id too: another user's item looks "not found", not "forbidden"
    item = db.scalar(select(CartItem).where(CartItem.id == item_id, CartItem.user_id == user.id))
    if item is None:
        raise NotFoundError("Cart item not found")
    db.delete(item)
    db.commit()