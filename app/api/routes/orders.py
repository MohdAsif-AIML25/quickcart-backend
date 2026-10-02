from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.models import Order
from app.schemas.order import OrderRead
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post(
    "/checkout",
    response_model=OrderRead,
    status_code=201,
    summary="Place an order from my cart",
    responses={400: {"description": "Cart is empty"}, 409: {"description": "Insufficient stock"}},
)
def checkout(user: CurrentUser, db: DbSession) -> Order:
    return order_service.checkout(db, user)


@router.get("/me", response_model=list[OrderRead], summary="List my orders")
def my_orders(user: CurrentUser, db: DbSession) -> list[Order]:
    return order_service.list_user_orders(db, user)