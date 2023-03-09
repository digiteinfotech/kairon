from fastapi import APIRouter, Security, Path
from starlette.requests import Request

from kairon import Utility
from kairon.shared.auth import Authentication
from kairon.api.models import (
    Response,
)
from kairon.shared.channels.whatsapp.bsp.factory import BusinessServiceProviderFactory
from kairon.shared.chat.models import ChannelRequest
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.constants import TESTER_ACCESS, DESIGNER_ACCESS, WhatsappBSPTypes
from kairon.shared.models import User
from kairon.shared.data.processor import MongoProcessor

router = APIRouter()
mongo_processor = MongoProcessor()


@router.post("/add", response_model=Response)
async def add_channel_config(
        request_data: ChannelRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Stores the channel config.
    """
    channel_endpoint = ChatDataProcessor.save_channel_config(
        request_data.dict(), current_user.get_bot(), current_user.get_user()
    )
    return Response(message='Channel added', data=channel_endpoint)


@router.get("/params", response_model=Response)
async def channels_params(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Stores the channel config.
    """
    return Response(data=Utility.system_metadata['channels'])


@router.get("/list", response_model=Response)
async def list_channel_config(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Returns list of channels for bot.
    """
    config = list(ChatDataProcessor.list_channel_config(current_user.get_bot()))
    return Response(data=config)


@router.get("/{name}/endpoint", response_model=Response)
async def get_channel_endpoint(
        name: str = Path(default=None, description="channel name", example="slack"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Retrieve channel endpoint.
    """
    return Response(data=ChatDataProcessor.get_channel_endpoint(name, current_user.get_bot()))


@router.delete("/{channel_id}", response_model=Response)
async def delete_channel_config(
        channel_id: str = Path(default=None, description="channel id", example="698705012345"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Deletes the channel config.
    """
    ChatDataProcessor.delete_channel_config(current_user.get_bot(), id=channel_id)
    return Response(message='Channel deleted')


@router.post("/whatsapp/{bsp_type}/post_process", response_model=Response)
async def refresh_bsp_credentials(
        bsp_type: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Recreate API key for 360Dialog and set webhook url.
    """
    provider = BusinessServiceProviderFactory.get_instance(bsp_type)(current_user.get_bot(), current_user.get_user())
    provider.validate()
    resp = provider.post_process()
    return Response(message='Credentials refreshed!', data=resp)


@router.post("/whatsapp/{bsp_type}/onboarding", response_model=Response)
async def initiate_platform_onboarding(
        request: Request,
        bsp_type: str = Path(default=None, description="Business service provider type",
                             example=WhatsappBSPTypes.bsp_360dialog.value),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    save the waba details
    """
    provider = BusinessServiceProviderFactory.get_instance(bsp_type)(current_user.get_bot(), current_user.get_user())
    provider.validate()
    channel_endpoint = provider.save_channel_config(**request.query_params)
    return Response(message='Channel added', data=channel_endpoint)
