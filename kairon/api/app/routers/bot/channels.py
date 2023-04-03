from fastapi import APIRouter, Security, Path
from starlette.requests import Request

from kairon import Utility
from kairon.events.definitions.message_broadcast import MessageBroadcastEvent
from kairon.shared.auth import Authentication
from kairon.api.models import (
    Response,
)
from kairon.shared.channels.whatsapp.bsp.factory import BusinessServiceProviderFactory
from kairon.shared.chat.models import ChannelRequest, MessageBroadcastRequest
from kairon.shared.chat.notifications.processor import MessageBroadcastProcessor
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.constants import TESTER_ACCESS, DESIGNER_ACCESS, WhatsappBSPTypes, EventRequestType
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


@router.post("/broadcast/message", response_model=Response)
async def add_message_broadcast_event(
        request: MessageBroadcastRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Creates a scheduled message broadcast event or triggers the event
     directly if it is not scheduled.
    """
    event_type = EventRequestType.trigger_async.value
    event = MessageBroadcastEvent(current_user.get_bot(), current_user.get_user())
    event.validate()
    if request.scheduler_config:
        event_type = EventRequestType.add_schedule.value
    notification_id = event.enqueue(event_type, config=request.dict())
    return Response(message="Broadcast added!", data={"msg_broadcast_id": notification_id})


@router.put("/broadcast/message/{msg_broadcast_id}", response_model=Response)
async def update_message_broadcast_event(
        msg_broadcast_id: str, request: MessageBroadcastRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Updates a scheduled message broadcast.
    """
    event = MessageBroadcastEvent(current_user.get_bot(), current_user.get_user())
    event.validate()
    event.enqueue(EventRequestType.update_schedule.value, msg_broadcast_id=msg_broadcast_id, config=request.dict())
    return Response(message="Broadcast updated!")


@router.get("/broadcast/message/list", response_model=Response)
async def retrieve_scheduled_message_broadcast(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Retrieves all message broadcasts scheduled in a bot.
    """
    data = list(MessageBroadcastProcessor.list_settings(current_user.get_bot()))
    return Response(data={"schedules": data})


@router.delete("/broadcast/message/{notification_id}", response_model=Response)
async def delete_scheduled_message_broadcast(
        notification_id: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Deletes a scheduled message broadcast.
    """
    event = MessageBroadcastEvent(current_user.get_bot(), current_user.get_user())
    event.delete_schedule(notification_id)
    return Response(message="Broadcast removed!")


@router.get("/broadcast/message/logs", response_model=Response)
async def retrieve_scheduled_message_broadcast_logs(
        request: Request,
        start_idx: int = 0, page_size: int = 10,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Retrieves logs of scheduled/one time message broadcasts in a bot.
    """
    log_filters = request.query_params._dict.copy()
    logs, total_count = MessageBroadcastProcessor.get_broadcast_logs(
        current_user.get_bot(), start_idx, page_size, **log_filters
    )
    return Response(data={"logs": logs, "total_count": total_count})
