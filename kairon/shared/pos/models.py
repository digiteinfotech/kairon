from pydantic import BaseModel
from typing import Optional, List

from kairon.shared.pos.constants import PageType


class ClientRequest(BaseModel):
    client_name: str


class LoginRequest(BaseModel):
    client_name: str
    page_type: PageType = PageType.pos_products.value


class ProductItem(BaseModel):
    product_id: int
    qty: int
    unit_price: float


class POSOrderRequest(BaseModel):
    products: List[ProductItem]
    partner_id: Optional[int] = None


class ResponseMessage(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None
