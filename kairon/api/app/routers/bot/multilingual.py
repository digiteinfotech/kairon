from kairon.events.definitions.multilingual import MultilingualEvent
from kairon.shared.multilingual.processor import MultilingualLogProcessor
from kairon.shared.multilingual.models import TranslationRequest
from kairon.shared.models import User
from fastapi import APIRouter, Security
from kairon.shared.auth import Authentication
from kairon.api.models import Response
from kairon.shared.constants import TESTER_ACCESS, DESIGNER_ACCESS
from kairon.shared.multilingual.utils.translator import Translator

router = APIRouter()


@router.get('/logs', response_model=Response)
async def get_multilingual_translation_logs(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Get multilingual translation logs
    """
    logs = list(MultilingualLogProcessor.get_logs(current_user.get_bot()))
    return Response(data=logs)


@router.post("/translate", response_model=Response)
async def multilingual_translate_bot(
        request_data: TranslationRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Translate source bot into destination language
    """
    event = MultilingualEvent(
        current_user.get_bot(), current_user.get_user(), dest_lang=request_data.dest_lang,
        translate_responses=request_data.translate_responses, translate_actions=request_data.translate_actions
    )
    event.validate()
    event.enqueue()
    return {"message": "Bot translation in progress! Check logs."}


@router.get("/languages", response_model=Response)
async def get_supported_languages(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Get supported languages for translation
    """
    return Response(data=Translator.get_supported_languages())
