from typing import Annotated

from fastapi import APIRouter, Path

from app.api.deps import CurrentUser, DbSession
from app.schemas.cart import CartItemAdd, CartItemRead, CartRead
from app.services import cart_service

router = APIRouter(prefix="/cart", tags=["Cart"])


@router.post(
    "/items",
    response_model=CartItemRead,
    status_code=201,
    summary="Add a product to the cart",
    responses={404: {"description": "Product not found"}, 409: {"description": "Not enough stock"}},
)
def add_cart_item(data: CartItemAdd, user: CurrentUser, db: DbSession) -> CartItemRead:
    return cart_service.add_item(db, user, data)


@router.get("", response_model=CartRead, summary="View my cart")
def get_cart(user: CurrentUser, db: DbSession) -> CartRead:
    return cart_service.get_cart(db, user)


@router.delete("/items/{item_id}", status_code=204, summary="Remove an item from my cart")
def remove_cart_item(
    item_id: Annotated[int, Path(gt=0)], user: CurrentUser, db: DbSession
) -> None:
    cart_service.remove_item(db, user, item_id)