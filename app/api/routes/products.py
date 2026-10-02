from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.product import PaginatedProducts
from app.services import product_service

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("", response_model=PaginatedProducts, summary="List active products")
def list_products(
    db: DbSession,
    page: Annotated[int, Query(ge=1, description="Page number, starting at 1")] = 1,
    limit: Annotated[int, Query(ge=1, le=100, description="Items per page (max 100)")] = 10,
    category: Annotated[str | None, Query(min_length=2, max_length=50, examples=["electronics"])] = None,
    search: Annotated[str | None, Query(min_length=1, max_length=100, description="Search name/description")] = None,
) -> PaginatedProducts:
    return product_service.list_products(db, page=page, limit=limit, category=category, search=search)