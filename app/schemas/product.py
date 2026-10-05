from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Price = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2, examples=["1499.00"])]


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200, examples=["Wireless Mouse"])
    description: str | None = Field(default=None, max_length=2000)
    price: Price
    stock: int = Field(default=0, ge=0, examples=[25])
    category: str = Field(min_length=2, max_length=50, examples=["electronics"])

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value

    @field_validator("category")
    @classmethod
    def normalize_category(cls, value: str) -> str:
        # Stored lowercase so the `?category=` filter is case-insensitive
        return value.strip().lower()


class ProductUpdate(BaseModel):
    """PATCH body: every field is optional; only the fields sent are changed."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    price: Price | None = None
    stock: int | None = Field(default=None, ge=0)
    category: str | None = Field(default=None, min_length=2, max_length=50)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value

    @field_validator("category")
    @classmethod
    def normalize_category(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else value

    @model_validator(mode="after")
    def reject_explicit_null(self) -> "ProductUpdate":
        # "Field not sent" and "field sent as null" both arrive here as None.
        # model_fields_set tells them apart: it holds only the fields the client sent.
        # These columns are NOT NULL, so an explicit null must be a 422, not a database error.
        for field in ("name", "price", "stock", "category", "is_active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    price: Decimal
    stock: int
    category: str
    image_url: str | None
    is_active: bool
    created_at: datetime


class PaginatedProducts(BaseModel):
    items: list[ProductRead]
    page: int
    limit: int
    total: int
    pages: int
