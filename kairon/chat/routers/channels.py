from typing import Text

from fastapi import APIRouter, Path, Security
from starlette.requests import Request

from kairon.chat.handlers.channels.factory import ChannelHandlerFactory
from kairon.shared.auth import Authentication
from kairon.shared.constants import ChannelTypes, CHAT_ACCESS
from kairon.shared.models import User

router = APIRouter()


@router.get("/{bot}/user/posts")
async def get_user_posts(
        request: Request,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=CHAT_ACCESS)
):
    from kairon.chat.handlers.channels.messenger import InstagramHandler
    handler = InstagramHandler(bot=current_user.get_bot(), user=current_user.get_user(), request=request)
    return await handler.get_user_posts()


@router.get("/{channel}/{bot}/{token}")
async def handle_validation_request_for_channel(
        request: Request,
        channel: ChannelTypes = Path(description="Channel name",
                                     examples=[ChannelTypes.WHATSAPP.value, ChannelTypes.SLACK.value]),
        bot: Text = Path(description="Bot id"),
        token: Text = Path(description="Token generated from api server"),
        current_user: User = Security(Authentication.authenticate_token_in_path_param, scopes=CHAT_ACCESS)
):
    """
    Receives webhook validation requests from channels and forwards them to their respective
    handlers (if that channel is configured).
    """
    ack = await ChannelHandlerFactory.get_handler(channel)(bot, current_user, request).validate()
    return ack


@router.post("/{channel}/{bot}/{token}")
async def get_agent_response_for_channel(
        request: Request,
        channel: ChannelTypes = Path(description="Channel name",
                                     examples=[ChannelTypes.WHATSAPP.value, ChannelTypes.SLACK.value]),
        bot: Text = Path(description="Bot id"),
        current_user: User = Security(Authentication.authenticate_token_in_path_param, scopes=CHAT_ACCESS)
):
    """
    Receives request from channels and forwards them to their respective handlers (if that channel is configured).
    An instant acknowledgement is sent and response of user message is retrieved
    in the background from model and sent back to the channel.
    """
    ack = await ChannelHandlerFactory.get_handler(channel)(bot, current_user, request).handle_message()
    return ack
