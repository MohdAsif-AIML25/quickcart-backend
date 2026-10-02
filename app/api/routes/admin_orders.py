from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, require_admin
from app.models import Order
from app.schemas.order import AdminOrderRead
from app.services import order_service

from fastapi import APIRouter, Depends, File, Path, UploadFile
from app.services import product_service, upload_service

router = APIRouter(prefix="/admin/orders", tags=["Admin - Orders"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[AdminOrderRead], summary="List all orders (admin)")
def list_orders(
    db: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[Order]:
    return order_service.list_all_orders(db, page=page, limit=limit)

@router.post(
    "/{product_id}/image",
    response_model=ProductRead,
    summary="Upload a product image (JPEG, PNG, WebP; max 2 MB)",
    responses={413: {"description": "File too large"}, 415: {"description": "Unsupported file type"}},
)
def upload_product_image(
    product_id: ProductId,
    db: DbSession,
    file: Annotated[UploadFile, File(description="JPEG, PNG or WebP image")],
) -> Product:
    product_service.get_product_or_404(db, product_id)
    image_url = upload_service.save_product_image(file)
    return product_service.set_product_image(db, product_id, image_url)