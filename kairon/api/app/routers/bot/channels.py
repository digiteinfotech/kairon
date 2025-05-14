from fastapi import APIRouter, Security, Path
from starlette.requests import Request

from kairon import Utility
from kairon.api.models import (
    Response, DictData,
)
from kairon.events.definitions.message_broadcast import MessageBroadcastEvent
from kairon.shared.auth import Authentication
from kairon.shared.channels.whatsapp.bsp.factory import BusinessServiceProviderFactory
from kairon.shared.chat.broadcast.processor import MessageBroadcastProcessor
from kairon.shared.chat.models import ChannelRequest, MessageBroadcastRequest
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.constants import TESTER_ACCESS, DESIGNER_ACCESS, WhatsappBSPTypes, EventRequestType, ChannelTypes
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.models import User

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
        name: str = Path(description="channel name", examples=["slack"]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Retrieve channel endpoint.
    """
    return Response(data=ChatDataProcessor.get_channel_endpoint(name, current_user.get_bot()))


@router.delete("/{channel_id}", response_model=Response)
async def delete_channel_config(
        channel_id: str = Path(description="channel id", examples=["698705012345"]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Deletes the channel config.
    """
    ChatDataProcessor.delete_channel_config(current_user.get_bot(), user=current_user.get_user(), id=channel_id)
    return Response(message='Channel deleted')


@router.post("/whatsapp/{bsp_type}/post_process", response_model=Response)
async def refresh_bsp_credentials(
        bsp_type: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
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
        bsp_type: str = Path(description="Business service provider type", examples=[WhatsappBSPTypes.bsp_360dialog.value]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    save the waba details
    """
    provider = BusinessServiceProviderFactory.get_instance(bsp_type)(current_user.get_bot(), current_user.get_user())
    provider.validate()
    channel_endpoint = provider.save_channel_config(**request.query_params)
    return Response(message='Channel added', data=channel_endpoint)


@router.post("/whatsapp/flows/{bsp_type}", response_model=Response)
async def add_whatsapp_flow(
        request_data: DictData,
        bsp_type: str = Path(description="Business service provider type",
                             examples=[WhatsappBSPTypes.bsp_360dialog.value]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Adds whatsapp flows for configured bsp account. New Flows are created as drafts.
    """
    provider = BusinessServiceProviderFactory.get_instance(bsp_type)(current_user.get_bot(), current_user.get_user())
    response = provider.add_whatsapp_flow(request_data.data, current_user.get_bot(), current_user.get_user())
    return Response(data=response)


@router.post("/whatsapp/flows/{bsp_type}/{flow_id}", response_model=Response)
async def edit_whatsapp_flow(
        request_data: DictData,
        flow_id: str = Path(description="flow id", examples=["594425479261596"]),
        bsp_type: str = Path(description="Business service provider type",
                             examples=[WhatsappBSPTypes.bsp_360dialog.value]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Edits whatsapp flows for configured bsp account. New Flows are created as drafts.
    """
    provider = BusinessServiceProviderFactory.get_instance(bsp_type)(current_user.get_bot(), current_user.get_user())
    response = provider.edit_whatsapp_flow(flow_id, request_data.data.get("flow_json"))
    return Response(data=response)


@router.get("/whatsapp/flows/{bsp_type}/{flow_id}", response_model=Response)
async def preview_whatsapp_flow(
        flow_id: str = Path(description="flow id", examples=["594425479261596"]),
        bsp_type: str = Path(description="Business service provider type",
                             examples=[WhatsappBSPTypes.bsp_360dialog.value]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Flows can be previewed through a public link generated with this endpoint.
    """
    provider = BusinessServiceProviderFactory.get_instance(bsp_type)(current_user.get_bot(), current_user.get_user())
    response = provider.preview_whatsapp_flow(flow_id)
    return Response(data=response)


@router.get("/whatsapp/flows/{bsp_type}/{flow_id}/assets", response_model=Response)
async def get_whatsapp_flow_assets(
        flow_id: str = Path(description="flow id", examples=["594425479261596"]),
        bsp_type: str = Path(description="Business service provider type",
                             examples=[WhatsappBSPTypes.bsp_360dialog.value]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Returns all assets attached to a specified flow with this endpoint.
    """
    provider = BusinessServiceProviderFactory.get_instance(bsp_type)(current_user.get_bot(), current_user.get_user())
    response = provider.get_whatsapp_flow_assets(flow_id)
    return Response(data=response)


@router.post("/whatsapp/flows/{bsp_type}/{flow_id}/deprecate", response_model=Response)
async def deprecate_whatsapp_flow(
        flow_id: str = Path(description="flow id", examples=["594425479261596"]),
        bsp_type: str = Path(description="Business service provider type",
                             examples=[WhatsappBSPTypes.bsp_360dialog.value]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Flow can be deprecated with this endpoint.
    """
    provider = BusinessServiceProviderFactory.get_instance(bsp_type)(current_user.get_bot(), current_user.get_user())
    response = provider.deprecate_whatsapp_flow(flow_id)
    return Response(data=response)


@router.get("/whatsapp/flows/{bsp_type}", response_model=Response)
async def retrieve_whatsapp_flows(
        request: Request,
        bsp_type: str = Path(description="Business service provider type",
                             examples=[WhatsappBSPTypes.bsp_360dialog.value]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Retrieves all whatsapp flows for configured bsp account.
    Query parameters passed are used as filters while retrieving these flows.
    """
    provider = BusinessServiceProviderFactory.get_instance(bsp_type)(current_user.get_bot(), current_user.get_user())
    flows = provider.list_whatsapp_flows(**request.query_params)
    return Response(data={"flows": flows})


@router.delete("/whatsapp/flows/{bsp_type}/{flow_id}", response_model=Response)
async def delete_whatsapp_flow(
        flow_id: str = Path(description="flow id", examples=["594425479261596"]),
        bsp_type: str = Path(description="Business service provider type",
                             examples=[WhatsappBSPTypes.bsp_360dialog.value]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Deletes whatsapp flow from configured bsp account.
    """
    provider = BusinessServiceProviderFactory.get_instance(bsp_type)(current_user.get_bot(), current_user.get_user())
    response = provider.delete_flow(flow_id)
    return Response(data=response)


@router.post("/whatsapp/flows/{bsp_type}/{flow_id}/publish", response_model=Response)
async def publish_whatsapp_flow(
        flow_id: str = Path(description="flow id", examples=["594425479261596"]),
        bsp_type: str = Path(description="Business service provider type",
                             examples=[WhatsappBSPTypes.bsp_360dialog.value]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Publishes whatsapp flow from configured bsp account.
    """
    provider = BusinessServiceProviderFactory.get_instance(bsp_type)(current_user.get_bot(), current_user.get_user())
    response = provider.publish_flow(flow_id)
    return Response(data=response)


@router.post("/whatsapp/templates/{bsp_type}", response_model=Response)
async def add_message_templates(
        request_data: DictData,
        bsp_type: str = Path(description="Business service provider type", examples=[WhatsappBSPTypes.bsp_360dialog.value]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Adds message templates for configured bsp account.
    """
    provider = BusinessServiceProviderFactory.get_instance(bsp_type)(current_user.get_bot(), current_user.get_user())
    response = provider.add_template(request_data.data, current_user.get_bot(), current_user.get_user())
    return Response(data=response)


@router.put("/whatsapp/templates/{bsp_type}/{template_id}", response_model=Response)
async def edit_message_templates(
        request_data: DictData,
        template_id: str = Path(description="template id", examples=["594425479261596"]),
        bsp_type: str = Path(description="Business service provider type", examples=[WhatsappBSPTypes.bsp_360dialog.value]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Edits message templates for configured bsp account.
    """
    provider = BusinessServiceProviderFactory.get_instance(bsp_type)(current_user.get_bot(), current_user.get_user())
    response = provider.edit_template(request_data.data, template_id),
    return Response(data=response)


@router.delete("/whatsapp/templates/{bsp_type}/{template_id}", response_model=Response)
async def delete_message_templates(
        template_id: str = Path(description="template id", examples=["594425479261596"]),
        bsp_type: str = Path(description="Business service provider type", examples=[WhatsappBSPTypes.bsp_360dialog.value]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Deletes message templates for configured bsp account.
    """
    provider = BusinessServiceProviderFactory.get_instance(bsp_type)(current_user.get_bot(), current_user.get_user())
    response = provider.delete_template(template_id)
    return Response(data=response)


@router.get("/whatsapp/templates/{bsp_type}/list", response_model=Response)
async def retrieve_message_templates(
        request: Request,
        bsp_type: str = Path(description="Business service provider type", examples=[WhatsappBSPTypes.bsp_360dialog.value]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Retrieves all message templates for configured bsp account.
    Query parameters passed are used as filters while retrieving these templates.
    """
    provider = BusinessServiceProviderFactory.get_instance(bsp_type)(current_user.get_bot(), current_user.get_user())
    templates = provider.list_templates(**request.query_params)
    return Response(data={"templates": templates})


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


@router.post("/broadcast/message/resend/{msg_broadcast_id}", response_model=Response)
async def resend_message_broadcast_event(
        msg_broadcast_id: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Resends a scheduled message broadcast.
    """
    event = MessageBroadcastEvent(current_user.get_bot(), current_user.get_user())
    event.validate_retry_broadcast(event_id=msg_broadcast_id)
    event.enqueue(EventRequestType.resend_broadcast.value, msg_broadcast_id=msg_broadcast_id)
    return Response(message="Resending Broadcast!")


@router.put("/broadcast/message/{msg_broadcast_id}", response_model=Response)
async def update_message_broadcast_event(
        msg_broadcast_id: str, request: MessageBroadcastRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Updates a scheduled message broadcast.
    """
    event = MessageBroadcastEvent(current_user.get_bot(), current_user.get_user())
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
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Retrieves logs of scheduled/one time message broadcasts in a bot.
    """
    log_filters = request.query_params._dict.copy()
    logs, total_count = MessageBroadcastProcessor.get_broadcast_logs(current_user.get_bot(), **log_filters)
    return Response(data={"logs": logs, "total_count": total_count})


@router.get("/{channel_type}/metrics", response_model=Response)
async def get_channel_metrics(
        channel_type: ChannelTypes,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Get Channel metrics (Failures/Successes).
    """
    return Response(data=MessageBroadcastProcessor.get_channel_metrics(channel_type, current_user.get_bot()))
