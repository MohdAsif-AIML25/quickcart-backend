from datetime import datetime 
from decimal import Decimal 

from pydantic import BaseModel, ConfigDict 

class OrderItemRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    product_id: int 
    quantity: int
    unit_price: Decimal 

class OrderRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id: int 
    status: str 
    total_amount: Decimal 
    created_at: datetime 
    items: list[OrderItemRead]

class AdminOrderRead(OrderRead):
    user_id: int 
    