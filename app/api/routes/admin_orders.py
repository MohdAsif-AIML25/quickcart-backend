from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, require_admin
from app.models import Order
from app.schemas.order import AdminOrderRead
from app.services import order_service

router = APIRouter(prefix="/admin/orders", tags=["Admin - Orders"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[AdminOrderRead], summary="List all orders (admin)")
def list_orders(
    db: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[Order]:
    return order_service.list_all_orders(db, page=page, limit=limit)
