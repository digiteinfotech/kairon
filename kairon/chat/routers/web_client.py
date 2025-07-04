import json
from typing import Text, Dict

from fastapi import APIRouter, Path, Security, Header, UploadFile, Form, File, HTTPException
from starlette.background import BackgroundTasks
from starlette.requests import Request
from starlette.responses import StreamingResponse

from kairon import Utility
from kairon.api.models import Response, TextData
from kairon.chat.utils import ChatUtils
from kairon.live_agent.live_agent import LiveAgent
from kairon.shared.auth import Authentication
from kairon.shared.chat.agent.agent_flow import AgenticFlow
from kairon.shared.chat.models import ChatRequest, AgenticFlowRequest
from kairon.shared.chat.user_media import UserMedia
from kairon.shared.constants import CHAT_ACCESS
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.models import User


router = APIRouter()


@router.post("/chat", response_model=Response)
async def get_agent_response_for_web_client(request: ChatRequest,
                                            x_telemetry_uid: Text = Header(None),
                                            x_telemetry_sid: Text = Header(None),
                                            current_user: User = Security(Authentication.get_current_user_and_bot,
                                                                          scopes=CHAT_ACCESS)):
    """
    Retrieves agent response for user message.
    """
    request.metadata = ChatUtils.add_telemetry_metadata(x_telemetry_uid, x_telemetry_sid, request.metadata)
    response = await ChatUtils.chat(request.data, current_user.bot_account, current_user.get_bot(),
                                    current_user.get_user(),
                                    current_user.is_integration_user, request.metadata)
    return {"data": response}

@router.post("/chat/media", response_model=Response)
async def get_agent_response_for_web_client2(
                                            data: str = Form(...),
                                            metadata: str = Form(...),
                                            files: list[UploadFile] = File(...),
                                            x_telemetry_uid: Text = Header(None),
                                            x_telemetry_sid: Text = Header(None),
                                            current_user: User = Security(Authentication.get_current_user_and_bot,
                                                                          scopes=CHAT_ACCESS)):
    """
    Retrieves agent response for user message.
    """
    data = json.loads(data)
    metadata = json.loads(metadata)
    metadata = ChatUtils.add_telemetry_metadata(x_telemetry_uid, x_telemetry_sid, metadata)
    response = await ChatUtils.chat(data, current_user.bot_account, current_user.get_bot(),
                                    current_user.get_user(),
                                    current_user.is_integration_user, metadata, files)
    return {"data": response}


@router.get("/chat/client/config/{token}", response_model=Response)
async def get_chat_client_config(
        request: Request,
        bot: Text = Path(description="Bot id"), token: Text = Path(description="Token generated from api server"),
        token_claims: Dict = Security(Authentication.validate_bot_specific_token, scopes=CHAT_ACCESS)
):
    """
    Retrieves chat client config of a bot.
    """
    config = MongoProcessor().get_client_config_using_uid(bot, token_claims)
    config = Utility.validate_domain(request, config)
    return {"data": config['config']}


@router.get("/conversation", response_model=Response)
async def get_session_coversation(
        bot: Text = Path(description="Bot id"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=CHAT_ACCESS)
):
    """
    Retrieves chat client config of a bot.
    """
    data, message = ChatUtils.get_last_session_conversation(bot, current_user.get_user())
    return {"data": data, "message": message}


@router.post("/agent/live/{destination}", response_model=Response)
async def send_message_to_live_agent_system(
        request: TextData,
        bot: Text = Path(description="Bot id"), destination: Text = Path(description="Token generated from api server"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=CHAT_ACCESS)
):
    """
    Retrieves chat client config of a bot.
    """
    return {"data": {"response": LiveAgent.from_bot(bot).send_message(request.data, destination)}}


@router.get("/reload", response_model=Response)
async def reload_model(
        background_tasks: BackgroundTasks, bot: Text = Path(description="Bot id"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=CHAT_ACCESS)
):
    """
    Retrieves chat client config of a bot.
    """
    background_tasks.add_task(ChatUtils.reload, bot, current_user.get_user())
    return {"message": "Reloading Model!"}


@router.get('/verify/chat', response_model=Response)
async def verity_auth(current_user: User = Security(Authentication.get_current_user_and_bot, scopes=CHAT_ACCESS)):
    return {"message": "verification successful", "data": {
        "sender_id": current_user.get_user(),
        "bot_id": current_user.get_bot()
    }}

@router.post('/exec/flow', response_model=Response)
async def execute_flow(
        request: AgenticFlowRequest,
        bot: Text = Path(description="Bot id"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=CHAT_ACCESS)
):
    """
    Retrieves chat client config of a bot.
    """
    flow = AgenticFlow(bot, request.slot_vals, request.sender_id)
    responses, errors = await flow.execute_rule(request.name)
    return {
        "data": {
            "responses": responses,
            "errors": errors,
        },
        "message": "Rule executed successfully!"
    }


@router.post('/chat/exec/flow/media', response_model=Response)
async def execute_flow_media(
        name: str = Form(...),
        sender_id: str = Form(...),
        slot_vals: str = Form('{}'),
        files: list[UploadFile] = File(...),
        bot: Text = Path(description="Bot id"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=CHAT_ACCESS)
):

    resp, errs = await ChatUtils.handle_media_agentic_flow(bot=bot,
                                                           sender_id=sender_id,
                                                           name=name,
                                                           slot_vals=slot_vals,
                                                           files=files)
    return {
        "data": {
            "responses": resp,
            "errors": errs,
        },
        "message": "Rule executed successfully!"
    }

@router.get('/chat/media/download/{media_id}', response_class=StreamingResponse)
async def media_download(
        bot: Text = Path(description="Bot id"),
        media_id: Text = Path(description="Id of the document"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=CHAT_ACCESS)
):
    try:
        file_stream, download_name, extension = await UserMedia.get_media_content_buffer(media_id)
        headers = {
            "Content-Disposition": f"attachment; filename={download_name}",
            "X-Content-Name": download_name,
            "X-Content-Extension": extension
        }
        return StreamingResponse(file_stream, media_type="application/octet-stream", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=404, detail="File not found or error downloading file") from e

