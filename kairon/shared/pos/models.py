from pydantic import BaseModel
from typing import Optional, List

from kairon.shared.pos.constants import PageType


class ClientRequest(BaseModel):
    client_name: str


class LoginRequest(BaseModel):
    client_name: str
    page_type: PageType = PageType.pos_products.value
    company_id: int = 1

class BranchRequest(BaseModel):
    branch_name: str
    street: str
    city: str
    state: str

class ProductItem(BaseModel):
    product_id: int
    qty: int
    unit_price: float


class POSOrderRequest(BaseModel):
    products: List[ProductItem]
    partner_id: Optional[int] = None
    company_id: int = 1


class ResponseMessage(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None
