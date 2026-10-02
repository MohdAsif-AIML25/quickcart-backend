from typing import Annotated

from fastapi import APIRouter, Depends, File, Path, UploadFile

from app.api.deps import DbSession, require_admin
from app.models import Product
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate
from app.services import product_service, upload_service

# Router-level dependency: every route below requires an admin token
router = APIRouter(
    prefix="/admin/products", tags=["Admin - Products"], dependencies=[Depends(require_admin)]
)

ProductId = Annotated[int, Path(gt=0)]


@router.post("", response_model=ProductRead, status_code=201, summary="Create a product")
def create_product(data: ProductCreate, db: DbSession) -> Product:
    return product_service.create_product(db, data)


@router.patch(
    "/{product_id}",
    response_model=ProductRead,
    summary="Update a product (only the fields sent)",
    responses={404: {"description": "Product not found"}},
)
def update_product(product_id: ProductId, data: ProductUpdate, db: DbSession) -> Product:
    return product_service.update_product(db, product_id, data)


@router.delete(
    "/{product_id}",
    status_code=204,
    summary="Deactivate a product (soft delete)",
    responses={404: {"description": "Product not found"}},
)
def delete_product(product_id: ProductId, db: DbSession) -> None:
    product_service.deactivate_product(db, product_id)


@router.post(
    "/{product_id}/image",
    response_model=ProductRead,
    summary="Upload a product image (JPEG, PNG, WebP; max 2 MB)",
    responses={
        404: {"description": "Product not found"},
        413: {"description": "File too large"},
        415: {"description": "Unsupported file type"},
    },
)
def upload_product_image(
    product_id: ProductId,
    db: DbSession,
    file: Annotated[UploadFile, File(description="JPEG, PNG or WebP image")],
) -> Product:
    product_service.get_product_or_404(db, product_id)  # fail before writing anything to disk
    image_url = upload_service.save_product_image(file)
    return product_service.set_product_image(db, product_id, image_url)
