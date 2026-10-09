from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Path

from app.api.deps import CurrentUser, DbSession
from app.models import Order
from app.schemas.order import CheckoutRequest, OrderRead
from app.services import notification_service, order_service

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post(
    "/checkout",
    response_model=OrderRead,
    status_code=201,
    summary="Place an order from my cart",
    description=(
        "Needs a delivery address and a payment method. Only `cod` (Cash on Delivery) is "
        "accepted: no payment gateway is integrated, so no card or UPI details are collected "
        "and the new order always starts with `payment_status: pending`."
    ),
    responses={400: {"description": "Cart is empty"}, 409: {"description": "Insufficient stock"}},
)
def checkout(
    data: CheckoutRequest, user: CurrentUser, db: DbSession, background_tasks: BackgroundTasks
) -> Order:
    order = order_service.checkout(db, user, data)
    background_tasks.add_task(
        notification_service.send_order_confirmation, order.id, user.email, str(order.total_amount)
    )
    return order


@router.get("/me", response_model=list[OrderRead], summary="List my orders")
def my_orders(user: CurrentUser, db: DbSession) -> list[Order]:
    return order_service.list_user_orders(db, user)


@router.get(
    "/{order_id}",
    response_model=OrderRead,
    summary="Get one of my orders",
    responses={404: {"description": "Order not found (or it belongs to another user)"}},
)
def get_my_order(order_id: Annotated[int, Path(gt=0)], user: CurrentUser, db: DbSession) -> Order:
    return order_service.get_user_order(db, user, order_id)
