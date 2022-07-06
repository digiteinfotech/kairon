from kairon.shared.multilingual.processor import MultilingualLogProcessor
from kairon.shared.multilingual.models import TranslationRequest
from kairon.shared.models import User
from fastapi import APIRouter, BackgroundTasks, Security
from kairon.shared.auth import Authentication
from kairon.api.models import Response
from kairon.shared.constants import TESTER_ACCESS, DESIGNER_ACCESS
from kairon.events.events import EventsTrigger

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
        background_tasks: BackgroundTasks, request_data: TranslationRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Translate source bot into destination language
    """
    MultilingualLogProcessor.is_event_in_progress(current_user.get_bot())
    MultilingualLogProcessor.is_limit_exceeded(current_user.get_bot())
    background_tasks.add_task(EventsTrigger.trigger_multilingual_translation, current_user.get_bot(),
                              current_user.get_user(), request_data.d_lang, request_data.translate_responses,
                              request_data.translate_actions)
    return {"message": "Bot translation in progress! Check logs."}
