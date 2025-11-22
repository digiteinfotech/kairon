from fastapi import APIRouter, Query, Security
from kairon.shared.pos.models import (
    RegisterRequest, CreateUserRequest, POSOrderRequest,
    LoginRequest
)
from kairon.api.models import Response
from kairon.shared.pos.processor import OdooProcessor
from kairon.shared.constants import ADMIN_ACCESS
from kairon.shared.auth import Authentication
from kairon.shared.models import User


odoo_processor = OdooProcessor()
router = APIRouter()


@router.get("/")
def index():
    return {"message": "Odoo Server is Running..."}


@router.post("/login")
def odoo_login(req: LoginRequest,
               current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)):
    """
    Returns session_id + cookies using /web/session/authenticate
    """
    data = odoo_processor.odoo_login(req.client_name, req.username, req.password)
    return Response(data=data)


@router.get("/session/info", response_model=Response)
def session_info(session_id: str,
                 current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)):
    """
    Returns session_id + cookies using /web/session/authenticate
    """
    data = odoo_processor.get_session_info(session_id)
    return Response(data=data)


@router.post("/register", response_model=Response)
def register(
        req: RegisterRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    result = odoo_processor.create_database(
        db_name=req.client_name,
        admin_username=req.admin_username,
        admin_password=req.admin_password,
        company=req.company,
        bot=current_user.get_bot(),
        user=current_user.get_user()
    )

    return Response(data=result)


@router.get("/client_details", response_model=Response)
def get_client_details(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    data = odoo_processor.get_client_details(current_user.get_bot())
    return Response(data=data)


@router.post("/install_module", response_model=Response)
def install_module(
    session_id: str = Query(..., description="Odoo session_id"),
    module_name: str = Query("point_of_sale", description="Module to install"),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    success, msg = odoo_processor.install_module(session_id, module_name)
    return Response(success=success, message=msg)


@router.post("/uninstall_module", response_model=Response)
def uninstall_module(
    session_id: str = Query(..., description="Odoo session_id"),
    module_name: str = Query("point_of_sale", description="Module to uninstall"),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    result = odoo_processor.uninstall_module_with_session(session_id, module_name)
    return Response(data=result)


@router.get("/user", response_model=Response)
def get_pos_users(
    session_id: str = Query(..., description="Odoo session_id"),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    res = odoo_processor.get_pos_users(session_id)
    return Response(data=res, message="POS users fetched successfully")


@router.post("/user", response_model=Response)
def create_user(
    req: CreateUserRequest,
    session_id: str = Query(..., description="Odoo session_id"),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    result = odoo_processor.create_user(
        session_id=session_id,
        login=req.login,
        password=req.password,
        name=req.name,
        partner_id=req.partner_id,
        pos_role=req.pos_role
    )
    return Response(data=result)


@router.delete("/user/{user_id}", response_model=Response)
def delete_user(
    user_id: int,
    session_id: str = Query(..., description="Odoo session_id"),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    result = odoo_processor.delete_user(session_id, user_id)
    return Response(data=result)


@router.put("/user/{user_id}/role", response_model=Response)
def update_user_role(
    user_id: int,
    pos_role: str = Query(..., description="POS ROLE (user / manager)"),
    session_id: str = Query(..., description="Odoo session_id"),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    result = odoo_processor.update_user_role(session_id, user_id, pos_role)
    return Response(data=result)


@router.post("/toggle_product/{product_id}", response_model=Response)
def toggle_product(
    product_id: int,
    session_id: str = Query(..., description="Odoo session_id"),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    res = odoo_processor.toggle_product_in_pos(
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
    res = odoo_processor.list_pos_orders(session_id, status)
    return Response(data={"data": res, "count": len(res)}, message="POS orders fetched")


@router.post("/pos_order", response_model=Response)
def create_order(req: POSOrderRequest, session_id: str = Query(...),
                 current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)):
    result = odoo_processor.create_pos_order(
        session_id=session_id,
        products=[p.dict() for p in req.products],
        partner_id=req.partner_id
    )
    return Response(data=result, message="POS order created")


@router.post("/pos_order/accept/{order_id}", response_model=Response)
def accept_order(
    order_id: int,
    session_id: str = Query(..., description="Odoo session_id"),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    res = odoo_processor.accept_pos_order(session_id, order_id)
    return {"success": res.get("accepted", False), "message": "Order accepted", "data": res}


@router.post("/pos_order/reject/{order_id}", response_model=Response)
def reject_order(
    order_id: int,
    session_id: str = Query(..., description="Odoo session_id"),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    res = odoo_processor.reject_pos_order(session_id, order_id)
    return {"success": res["status"] == "cancelled", "message": "Order rejected", "data": res}


@router.get("/product", response_model=Response)
async def get_pos_products(
    session_id: str = Query(..., description="Odoo session_id"),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    products = odoo_processor.get_pos_products(session_id)
    return {"success": True, "count": len(products), "data": products}
