import math

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models import Product
from app.schemas.product import PaginatedProducts, ProductCreate, ProductRead, ProductUpdate


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
