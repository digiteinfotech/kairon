from typing import Text

from fastapi import APIRouter, Path, Security
from starlette.requests import Request
from starlette.responses import Response as XMLResponse

from kairon.chat.handlers.channels.voice import VoiceHandler
from kairon.shared.auth import Authentication
from kairon.shared.constants import CHAT_ACCESS
from kairon.shared.models import User

router = APIRouter()

_EMPTY_TWIML = "<?xml version='1.0' encoding='UTF-8'?><Response/>"

_HEADERS = {"Content-Type": "text/xml; charset=utf-8"}

@router.post("/{bot}/channel/voice/{provider}/call/{token}")
async def handle_incoming_voice_call(
        request: Request,
        bot: Text = Path(description="Bot id"),
        provider: Text = Path(description="Voice provider name (e.g. twilio)"),
        token: Text = Path(description="Channel integration token"),
        current_user: User = Security(Authentication.authenticate_token_in_path_param, scopes=CHAT_ACCESS),
):
    voice_response = await VoiceHandler(bot, current_user, request, provider).handle_incoming_call()
    return XMLResponse(content=voice_response, media_type="application/xml", headers=_HEADERS)


@router.post("/{bot}/channel/voice/{provider}/process/{token}")
async def handle_voice_call_processing(
        request: Request,
        bot: Text = Path(description="Bot id"),
        provider: Text = Path(description="Voice provider name (e.g. twilio)"),
        token: Text = Path(description="Channel integration token"),
        current_user: User = Security(Authentication.authenticate_token_in_path_param, scopes=CHAT_ACCESS),
):
    voice_response = await VoiceHandler(bot, current_user, request, provider).handle_call_processing()
    return XMLResponse(content=voice_response, media_type="application/xml", headers=_HEADERS)


@router.post("/{bot}/channel/voice/{provider}/call/status/{token}")
async def handle_voice_call_status(
        request: Request,
        bot: Text = Path(description="Bot id"),
        provider: Text = Path(description="Voice provider name (e.g. twilio)"),
        token: Text = Path(description="Channel integration token"),
        current_user: User = Security(Authentication.authenticate_token_in_path_param, scopes=CHAT_ACCESS),
):
    await VoiceHandler(bot, current_user, request, provider).handle_call_status()
    return XMLResponse(content=_EMPTY_TWIML, media_type="application/xml", headers=_HEADERS)
