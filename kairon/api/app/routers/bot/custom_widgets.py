from typing import Text

from fastapi import APIRouter, Security, Path
from starlette.requests import Request

from kairon.shared.auth import Authentication
from kairon.api.models import Response
from kairon.shared.constants import ADMIN_ACCESS, VIEW_ACCESS, TESTER_ACCESS
from kairon.shared.custom_widgets.models import CustomWidgetsRequest, GlobalFilterConfigRequest
from kairon.shared.custom_widgets.processor import CustomWidgetsProcessor
from kairon.shared.models import User
from kairon.shared.data.processor import MongoProcessor

router = APIRouter()
mongo_processor = MongoProcessor()


@router.post("/custom", response_model=Response)
async def add_custom_widget(
        request_data: CustomWidgetsRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Save config for custom widget.
    """
    return Response(
        message='Widget config added!',
        data=CustomWidgetsProcessor.save_config(request_data.dict(), current_user.get_bot(), current_user.get_user())
    )


@router.put("/custom/{widget_id}", response_model=Response)
async def update_custom_widget(
        request_data: CustomWidgetsRequest,
        widget_id: Text = Path(description="Configuration id"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Update config for custom widget.
    """
    CustomWidgetsProcessor.edit_config(widget_id, request_data.dict(), current_user.get_bot(), current_user.get_user())
    return Response(message='Widget config updated!')


@router.get("/custom/list", response_model=Response)
async def list_custom_widgets(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=VIEW_ACCESS)
):
    """
    List only config id of all custom widgets.
    """
    return Response(data={"widgets": CustomWidgetsProcessor.list_widgets(current_user.get_bot())})


@router.get("/custom", response_model=Response)
async def get_custom_widget_config(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Retrieve config for all custom widgets.
    """
    return Response(data={"widgets": list(CustomWidgetsProcessor.get_config(current_user.get_bot()))})


@router.delete("/custom/{widget_id}", response_model=Response)
async def delete_custom_widget(
        widget_id: Text = Path(description="Configuration id"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Delete a particular custom widget.
    """
    CustomWidgetsProcessor.delete_config(widget_id, current_user.get_bot(), user=current_user.get_user())
    return Response(message='Widget config removed!')


@router.get("/custom/trigger/{widget_id}", response_model=Response)
async def trigger_widget(
        request: Request,
        widget_id: str = Path(description="Custom widget configuration id."),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=VIEW_ACCESS)
):
    """
    Trigger widget config to retrieve data.
    """
    filters = dict(request.query_params.multi_items())
    data, msg = CustomWidgetsProcessor.trigger_widget(widget_id, current_user.get_bot(), current_user.get_user(), filters, False)
    return {"data": data, "message": msg}


@router.get("/custom/logs/all", response_model=Response)
async def get_logs(
        start_idx: int = 0, page_size: int = 10,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Retrieve logs for widgets triggered in the past.
    """
    data = list(CustomWidgetsProcessor.get_logs(current_user.get_bot(), start_idx=start_idx, page_size=page_size))
    return {"data": {"logs": data, "total": CustomWidgetsProcessor.get_row_cnt(current_user.get_bot())}}


@router.post("/global_filter_config", response_model=Response)
async def add_global_filter_config(
        request_data: GlobalFilterConfigRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Save config for custom widget.
    """
    return Response(
        message='Global Filter config added!',
        data=CustomWidgetsProcessor.save_global_filter_config(request_data.dict(), current_user.get_bot(), current_user.get_user())
    )

@router.put("/global_filter_config", response_model=Response)
async def update_global_filter_config(
        request_data: GlobalFilterConfigRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Update global config for custom widget.
    """
    CustomWidgetsProcessor.update_global_filter_config(current_user.get_bot(), request_data.dict(), current_user.get_user())
    return Response(message='Global Filter config updated!')

@router.get("/global_filter_config", response_model=Response)
async def get_global_filter_config(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Retrieve global config for the custom widget.
    """
    return Response(data={"global_config": CustomWidgetsProcessor.get_global_filter_config(current_user.get_bot())})

@router.delete("/global_filter_config", response_model=Response)
async def delete_global_filter_config(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Delete global config for the custom widget.
    """
    CustomWidgetsProcessor.delete_global_filter_config(current_user.get_bot())
    return Response(message='Global Filter config removed!')


