import math

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models import Product
from app.schemas.product import PaginatedProducts, ProductCreate, ProductRead, ProductUpdate
from app.services.cache_service import invalidate_product_cache


def _escape_like(value: str) -> str:
    """Treat % and _ typed by users as literal characters, not wildcards."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_products(
    db: Session, *, page: int, limit: int, category: str | None, search: str | None
) -> PaginatedProducts:
    filters = [Product.is_active.is_(True)]
    if category:
        filters.append(Product.category == category.strip().lower())
    if search:
        pattern = f"%{_escape_like(search.strip())}%"
        filters.append(
            or_(
                Product.name.ilike(pattern, escape="\\"),
                Product.description.ilike(pattern, escape="\\"),
            )
        )

    total = db.scalar(select(func.count()).select_from(Product).where(*filters)) or 0
    products = db.scalars(
        select(Product)
        .where(*filters)
        .order_by(Product.id)  # stable order = stable pages
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()

    return PaginatedProducts(
        items=[ProductRead.model_validate(p) for p in products],
        page=page,
        limit=limit,
        total=total,
        pages=math.ceil(total / limit) if total else 0,
    )


def get_product_or_404(db: Session, product_id: int, *, active_only: bool = False) -> Product:
    product = db.get(Product, product_id)
    if product is None or (active_only and not product.is_active):
        raise NotFoundError("Product not found")
    return product


def create_product(db: Session, data: ProductCreate) -> Product:
    product = Product(**data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    invalidate_product_cache()  # cached listings are stale now
    return product


def update_product(db: Session, product_id: int, data: ProductUpdate) -> Product:
    product = get_product_or_404(db, product_id)
    # exclude_unset: only fields the client actually sent (PATCH semantics)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    invalidate_product_cache()
    return product


def deactivate_product(db: Session, product_id: int) -> None:
    """Soft delete: old orders still reference the product, so the row must stay."""
    product = get_product_or_404(db, product_id)
    product.is_active = False
    db.commit()
    invalidate_product_cache()


def set_product_image(db: Session, product_id: int, image_url: str) -> Product:
    product = get_product_or_404(db, product_id)
    product.image_url = image_url
    db.commit()
    db.refresh(product)
    invalidate_product_cache()
    return product
