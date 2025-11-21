from pydantic import BaseModel
from typing import Optional, List


class LoginRequest(BaseModel):
    client_name: str
    username: str
    password: str


class RegisterRequest(BaseModel):
    client_name: str
    admin_username: str
    admin_password: str
    company: str = None


class CreateUserRequest(BaseModel):
    db_name: str
    login: str
    password: str
    name: str
    partner_id: Optional[int] = None
    pos_role: str = "user"  # user / manager


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
