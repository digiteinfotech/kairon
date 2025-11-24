from pydantic import BaseModel
from typing import Optional, List


class LoginRequest(BaseModel):
    client_name: str
    username: str
    password: str


class RegisterRequest(BaseModel):
    client_name: str


class ProductItem(BaseModel):
    product_id: int
    qty: int
    unit_price: float


class POSOrderRequest(BaseModel):
    db_name: str
    products: List[ProductItem]
    partner_id: Optional[int] = None


class ResponseMessage(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None


class DeleteDBRequest(BaseModel):
    client_name: str

