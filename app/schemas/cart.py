from decimal import Decimal

from pydantic import BaseModel, Field

MAX_QUANTITY_PER_ITEM=100

class CartItemAdd(BaseModel):
    product_id: int=Field(gt=0,examples=[1])
    quantity: int= Field(default=1,ge=1,le=MAX_QUANTITY_PER_ITEM, examples=[2])

class CartItemRead(BaseModel):
    id: int
    product_id: int
    product_name: str
    unit_price: Decimal
    quantity: int
    subtotal: Decimal

class CartRead(BaseModel):
    items: list[CartItemRead]
    total_items: int
    total_amount: Decimal
