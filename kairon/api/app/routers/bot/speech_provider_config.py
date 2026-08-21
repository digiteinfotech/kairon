from typing import Optional

from fastapi import APIRouter, Security, Query
from pydantic import BaseModel

from kairon.api.models import Response
from kairon.shared.auth import Authentication
from kairon.shared.constants import DESIGNER_ACCESS, TESTER_ACCESS
from kairon.shared.models import User
from kairon.shared.voice.processor import SpeechProviderConfigProcessor

router = APIRouter()


class SpeechProviderConfigRequest(BaseModel):
    provider: str
    metadata: dict = {}
    secrets: dict = {}


@router.post("/add", response_model=Response)
async def add_speech_provider_config(
    request_data: SpeechProviderConfigRequest,
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """Create or update a bot-scoped STT/TTS provider configuration (BYOK)."""
    bot = current_user.get_bot()
    doc_id = SpeechProviderConfigProcessor.save(
        provider=request_data.provider,
        scope="bot",
        bot_id=bot,
        metadata=request_data.metadata,
        secrets=request_data.secrets,
        user=current_user.get_user(),
    )
    return Response(message="Voice provider config saved", data={"id": doc_id})


@router.get("/list", response_model=Response)
async def list_speech_provider_configs(
    provider: Optional[str] = Query(default=None),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS),
):
    """List all STT/TTS provider configurations available to this bot (bot-scoped + global)."""
    bot = current_user.get_bot()
    configs = SpeechProviderConfigProcessor.list_available(bot_id=bot, provider=provider)
    return Response(data=configs)


@router.get("/{config_id}", response_model=Response)
async def get_speech_provider_config(
    config_id: str,
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS),
):
    """Get a single provider config document by id (secrets masked)."""
    config = SpeechProviderConfigProcessor.get(config_id, mask_secrets=True)
    return Response(data=config)


@router.put("/{config_id}", response_model=Response)
async def update_speech_provider_config(
    config_id: str,
    request_data: SpeechProviderConfigRequest,
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """Update metadata and/or secrets for a bot-scoped provider config."""
    bot = current_user.get_bot()
    doc_id = SpeechProviderConfigProcessor.save(
        provider=request_data.provider,
        scope="bot",
        bot_id=bot,
        metadata=request_data.metadata,
        secrets=request_data.secrets,
        user=current_user.get_user(),
    )
    return Response(message="Voice provider config updated", data={"id": doc_id})


@router.delete("/{config_id}", response_model=Response)
async def delete_speech_provider_config(
    config_id: str,
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """Soft-delete a bot-scoped provider config."""
    SpeechProviderConfigProcessor.delete(config_id)
    return Response(message="Voice provider config deleted")
