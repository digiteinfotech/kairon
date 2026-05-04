from fastapi import APIRouter, Query, Security, Path, BackgroundTasks

from kairon import Utility
from kairon.pos.definitions.factory import POSFactory
from kairon.shared.pos.constants import POSType, OdooPOSActions, OdooPOSMenus
from kairon.shared.pos.models import (
    LoginRequest, ClientRequest, POSOrderRequest, BranchRequest, UserAccessRequest
)
from kairon.api.models import Response
from kairon.shared.pos.processor import POSProcessor
from kairon.shared.constants import ADMIN_ACCESS
from kairon.shared.auth import Authentication
from kairon.shared.models import User


pos_processor = POSProcessor()
router = APIRouter()


@router.post("/login")
def pos_login(req: LoginRequest,
              pos_type: POSType = Path(description="pos type", examples=["odoo"]),
              current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)):
    """
    Returns session_id + cookies using /web/session/authenticate
    """
    pos_instance = POSFactory.get_instance(pos_type)
    response = pos_instance().authenticate(client_name=req.client_name, page_type=req.page_type, bot=current_user.get_bot(), company_id=req.company_id)

    return response


@router.post("/register", response_model=Response)
def register(
        req: ClientRequest,
        pos_type: POSType = Path(description="pos type", examples=["odoo"]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    pos_instance = POSFactory.get_instance(pos_type)
    data = pos_instance().onboarding(
        client_name=req.client_name,
        bot=current_user.get_bot(),
        user=current_user.get_user()
    )

    return Response(data=data)

@router.post("/create/branch", response_model=Response)
def create_branch(
        req: BranchRequest,
        session_id: str = Query(..., description="Odoo session_id"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    result = pos_processor.create_branch(
        session_id=session_id,
        branch_name=req.branch_name,
        street=req.street,
        city=req.city,
        state=req.state,
        bot = current_user.get_bot(),
        user = current_user.get_user()
    )
    return Response(data=result, message="Branch created")

@router.delete("/client/delete", response_model=Response)
def delete_client(
        req: ClientRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    result = pos_processor.drop_client(
        client_name=req.client_name,
    )

    return Response(data=result)


@router.get("/client_name", response_model=Response)
def get_client_name(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    data = pos_processor.get_client_details(current_user.get_bot())
    return Response(data={"client_name": data.get("client_name"), "branches": data.get("branches",None)})


@router.post("/toggle_product/{product_id}", response_model=Response)
def toggle_product(
    product_id: int,
    session_id: str = Query(..., description="Odoo session_id"),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    res = pos_processor.toggle_product_in_pos(
        session_id=session_id,
        product_id=product_id
    )
    return Response(data=res, message=f"Product toggled to {'ON' if res['available_in_pos'] else 'OFF'}")


@router.get("/pos_order", response_model=Response)
def list_pos_orders(
    session_id: str = Query(..., description="Odoo session_id"),
    status: str | None = Query(None, description="Filter by POS order state"),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    res = pos_processor.list_pos_orders(session_id, status)
    return Response(data={"data": res, "count": len(res)}, message="POS orders fetched")


@router.post("/pos_order", response_model=Response)
async def create_order(background_tasks: BackgroundTasks, req: POSOrderRequest, session_id: str = Query(...),
                 current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)):
    result = pos_processor.create_pos_order(
        session_id=session_id,
        products=[p.dict() for p in req.products],
        partner_id=req.partner_id,
        company_id=req.company_id
    )

    if result["status"] == "created":
        base_url = Utility.environment["pos"]["odoo"]["odoo_url"]
        action = OdooPOSActions.ACTION_POS_ORDER_LIST.value
        menu = OdooPOSMenus.MENU_POS_ORDERS.value
        company_id = req.company_id
        orders_link = f"{base_url}/web#action={action}&model=pos.order&view_type=list&cids={company_id}&menu_id={menu}"
        order = result.get("order_id", {})

        background_tasks.add_task(
            pos_processor.send_notification,
            {
                "type": "link",
                "link": orders_link,
                "botId": current_user.get_bot(),
                "message": pos_processor.get_pos_notification_message(),
                "posType": POSType.odoo.value,
                "order_id": order.get("id"),
                "pos_reference": order.get("pos_reference"),
                "status": result.get("status")
            },
            current_user.get_bot()
        )
    return Response(data=result, message="POS order created")

@router.post("/pos_order/accept/{order_id}", response_model=Response)
def accept_order(
    order_id: int,
    session_id: str = Query(..., description="Odoo session_id"),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    res = pos_processor.accept_pos_order(session_id, order_id)
    return Response(message="Order accepted", data=res)


@router.post("/pos_order/reject/{order_id}", response_model=Response)
def reject_order(
    order_id: int,
    session_id: str = Query(..., description="Odoo session_id"),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    res = pos_processor.reject_pos_order(session_id, order_id)
    return Response(message="Order rejected", data=res)


@router.get("/product", response_model=Response)
async def get_pos_products(
    session_id: str = Query(..., description="Odoo session_id"),
    return_all: bool = Query(default=False, description="Flag to return all products or not"),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    products = pos_processor.get_pos_products(session_id, return_all)
    return Response(data={"count": len(products), "data": products})


@router.post("/invalidate/session", response_model=Response)
def invalidate_session_api(session_id: str = Query(..., description="Odoo session_id")):
    """
    Invalidate an Odoo session_id by calling /web/session/destroy.
    """

    pos_processor.invalidate_session(session_id)
    return Response(message="Session invalidated successfully")

@router.post("/user/access", response_model=Response)
async def get_user_access(
    req: UserAccessRequest,
    session_id: str,
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    users = pos_processor.get_user_branch_access(session_id, req.db_name, req.password)
    return Response(data=users)