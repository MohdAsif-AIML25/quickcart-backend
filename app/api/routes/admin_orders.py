from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import AdminUser, DbSession, require_admin
from app.models import Order
from app.schemas.order import AdminOrderRead, AdminOrderUpdate
from app.services import order_service

# Router-level dependency: every route below requires an admin token
router = APIRouter(prefix="/admin/orders", tags=["Admin - Orders"], dependencies=[Depends(require_admin)])

OrderId = Annotated[int, Path(gt=0)]


@router.get("", response_model=list[AdminOrderRead], summary="List all orders (admin)")
def list_orders(
    db: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[Order]:
    return order_service.list_all_orders(db, page=page, limit=limit)


@router.patch(
    "/{order_id}",
    response_model=AdminOrderRead,
    summary="Update order status and/or estimated delivery date",
    description=(
        "Allowed status changes: `confirmed` → `processing` or `cancelled`; "
        "`processing` → `shipped` or `cancelled`; `shipped` → `delivered`. "
        "`delivered` and `cancelled` are final. Cancelling returns the stock (once). "
        "Becoming `delivered` records `delivered_at`. `payment_status` is never changed here."
    ),
    responses={
        400: {"description": "Estimated delivery date is earlier than the order date"},
        404: {"description": "Order not found"},
        409: {"description": "Status change not allowed, or the order is already final"},
    },
)
def update_order(order_id: OrderId, data: AdminOrderUpdate, db: DbSession) -> Order:
    return order_service.update_order(db, order_id, data)


@router.delete(
    "/{order_id}",
    status_code=204,
    summary="Delete an order (soft delete, returns the stock)",
    description=(
        "Only a `confirmed` order can be deleted. The database row is kept, the order "
        "disappears from all order listings, and its units go back into stock exactly once."
    ),
    responses={
        404: {"description": "Order not found or already deleted"},
        409: {"description": "Order is no longer in the confirmed status"},
    },
)
def delete_order(order_id: OrderId, admin: AdminUser, db: DbSession) -> None:
    order_service.delete_order(db, order_id, admin)
