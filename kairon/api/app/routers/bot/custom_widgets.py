from typing import Text

from fastapi import APIRouter, Security, Path
from kairon.shared.auth import Authentication
from kairon.api.models import Response
from kairon.shared.constants import ADMIN_ACCESS, VIEW_ACCESS
from kairon.shared.custom_widgets.models import CustomWidgetsRequest
from kairon.shared.custom_widgets.processor import CustomWidgetsProcessor
from kairon.shared.models import User
from kairon.shared.data.processor import MongoProcessor

router = APIRouter()
mongo_processor = MongoProcessor()


@router.post("/add", response_model=Response)
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


@router.put("/update/{widget_id}", response_model=Response)
async def update_custom_widget(
        request_data: CustomWidgetsRequest,
        widget_id: Text = Path(default=None, description="Configuration id"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Update config for custom widget.
    """
    CustomWidgetsProcessor.edit_config(widget_id, request_data.dict(), current_user.get_bot(), current_user.get_user())
    return Response(message='Widget config updated!')


@router.get("/list", response_model=Response)
async def list_custom_widgets(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=VIEW_ACCESS)
):
    """
    List custom widgets.
    """
    return Response(data={"widgets": CustomWidgetsProcessor.list_widgets(current_user.get_bot())})


@router.get("/{widget_id}", response_model=Response)
async def get_custom_widget_config(
        widget_id: Text = Path(default=None, description="Configuration id"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Retrieve config for a particular custom widget.
    """
    return Response(data={"widget_config": CustomWidgetsProcessor.get_config(widget_id, current_user.get_bot())})


@router.delete("/remove/{widget_id}", response_model=Response)
async def delete_custom_widget(
        widget_id: Text = Path(default=None, description="Configuration id"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Delete a particular custom widget.
    """
    CustomWidgetsProcessor.delete_config(widget_id, current_user.get_bot())
    return Response(message='Widget config removed!')


@router.get("/trigger/{widget_id}", response_model=Response)
async def trigger_widget(
        widget_id: str = Path(default=None, description="Custom widget configuration id."),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=VIEW_ACCESS)
):
    """
    Trigger widget config to retrieve data.
    """
    data, msg = CustomWidgetsProcessor.trigger_widget(widget_id, current_user.get_bot(), current_user.get_user(), False)
    return {"data": data, "message": msg}
