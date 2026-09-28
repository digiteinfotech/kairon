from typing import Optional

from fastapi import APIRouter, Security, Query

from kairon.api.models import Response
from kairon.shared.auth import Authentication
from kairon.shared.constants import TESTER_ACCESS, DESIGNER_ACCESS
from kairon.shared.data.customer_order_processor import CustomerOrderProcessor
from kairon.shared.data.data_models import (
    UpsertCustomerRequest,
    AddressRequest,
    CreateOrderRequest,
    UpdateOrderStatusRequest,
    FilterOrdersRequest,
)
from kairon.shared.data.data_objects import CustomerDetails

router = APIRouter()

@router.post("/customer", response_model=Response)
async def upsert_customer(
        bot: str,
        request_data: UpsertCustomerRequest,
        current_user: CustomerDetails = Security(Authentication.validate_store_page_token, scopes=DESIGNER_ACCESS),
):
    """Upsert a customer record. Decrypts identifier at boundary; stores plain sender_id."""
    result = CustomerOrderProcessor.upsert_customer(
        bot=bot,
        sender_id=request_data.sender_id,
        persona_type=request_data.persona_type,
        payload=request_data.dict(exclude={"sender_id", "persona_type"}, exclude_none=True),
    )
    return Response(data=result)


@router.get("/customer", response_model=Response)
async def get_customer(
        bot: str,
        sender_id: str = Query(description="Encrypted sender identifier"),
        current_user: CustomerDetails = Security(Authentication.validate_store_page_token, scopes=TESTER_ACCESS),
):
    """Fetch a customer. Returns re-encrypted user_id."""
    result = CustomerOrderProcessor.get_customer(
        bot=bot,
        sender_id=sender_id,
    )
    return Response(data=result)


@router.get("/customers", response_model=Response)
async def list_customers(
        bot: str,
        persona_type: Optional[str] = Query(default=None),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        current_user: CustomerDetails = Security(Authentication.validate_store_page_token, scopes=TESTER_ACCESS),
):
    """List customers for this bot."""
    result = CustomerOrderProcessor.list_customers(
        bot=bot,
        persona_type=persona_type,
        page=page,
        page_size=page_size,
    )
    return Response(data=result)


@router.put("/customer/address", response_model=Response)
async def update_address(
        bot: str,
        sender_id: str = Query(description="Encrypted sender identifier"),
        request_data: AddressRequest = ...,
        current_user: CustomerDetails = Security(Authentication.validate_store_page_token, scopes=DESIGNER_ACCESS),
):
    """Add or replace an address entry for a customer (matched by label)."""
    result = CustomerOrderProcessor.update_address(
        bot=bot,
        sender_id=sender_id,
        address_payload=request_data.dict(),
    )
    return Response(data=result)


@router.delete("/customer", response_model=Response)
async def delete_customer(
        bot: str,
        sender_id: str = Query(description="Encrypted sender identifier"),
        current_user: CustomerDetails = Security(Authentication.validate_store_page_token, scopes=DESIGNER_ACCESS),
):
    """Soft-delete a customer (sets status=False)."""
    CustomerOrderProcessor.delete_customer(
        bot=bot,
        sender_id=sender_id,
    )
    return Response(message="Customer deleted")


@router.post("/order", response_model=Response)
async def create_order(
        bot: str,
        request_data: CreateOrderRequest,
        current_user: CustomerDetails = Security(Authentication.validate_store_page_token, scopes=DESIGNER_ACCESS),
):
    """Create an order tied to an existing customer. Fails if customer not found."""
    result = CustomerOrderProcessor.create_order(
        bot=bot,
        sender_id=request_data.sender_id,
        persona_type=request_data.persona_type,
        callback_identifier=request_data.callback_identifier,
        order_payload=request_data.order_details,
    )
    return Response(data=result)


@router.get("/order/{order_id}", response_model=Response)
async def get_order(
        bot: str,
        order_id: str,
        current_user: CustomerDetails = Security(Authentication.validate_store_page_token, scopes=TESTER_ACCESS),
):
    """Fetch a single order by ID."""
    result = CustomerOrderProcessor.get_order(
        bot=bot,
        order_id=order_id,
    )
    return Response(data=result)


@router.patch("/order/{order_id}/status", response_model=Response)
async def update_order_status(
        bot: str,
        order_id: str,
        request_data: UpdateOrderStatusRequest,
        current_user: CustomerDetails = Security(Authentication.validate_store_page_token, scopes=DESIGNER_ACCESS),
):
    """Advance order lifecycle status. Validates allowed transitions."""
    result = CustomerOrderProcessor.update_order_status(
        bot=bot,
        order_id=order_id,
        new_status=request_data.status,
    )
    return Response(data=result)


@router.get("/orders", response_model=Response)
async def list_orders_for_customer(
        bot: str,
        sender_id: str = Query(description="Encrypted sender identifier"),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        current_user: CustomerDetails = Security(Authentication.validate_store_page_token, scopes=TESTER_ACCESS),
):
    """List all orders for a customer, sorted by created_at desc."""
    result = CustomerOrderProcessor.list_orders_for_customer(
        bot=bot,
        sender_id=sender_id,
        page=page,
        page_size=page_size,
    )
    return Response(data=result)


@router.post("/orders/filter", response_model=Response)
async def filter_orders(
        bot: str,
        request_data: FilterOrdersRequest,
        current_user: CustomerDetails = Security(Authentication.validate_store_page_token, scopes=TESTER_ACCESS),
):
    """Filter orders via filterable_attrs attribute pattern. Never queries order_details.* directly."""
    result = CustomerOrderProcessor.filter_orders(
        bot=bot,
        persona_type=request_data.persona_type,
        filters=request_data.filters,
        page=request_data.page,
        page_size=request_data.page_size,
    )
    return Response(data=result)
