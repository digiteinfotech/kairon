from kairon.events.definitions.data_generation import DataGenerationEvent
from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.data.training_data_generation_processor import TrainingDataGenerationProcessor
from kairon.shared.models import User
from fastapi import APIRouter, Security
from kairon.shared.auth import Authentication
from kairon.api.models import Response
from kairon.shared.constants import TESTER_ACCESS, DESIGNER_ACCESS
from kairon.shared.multilingual.utils.translator import Translator

router = APIRouter()


@router.post("/website", response_model=Response)
async def data_generation_from_website(
        website_url: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Starts training data generation for by taking website url
    """
    event = DataGenerationEvent(
        current_user.get_bot(), current_user.get_user(), website_url=website_url
    )
    event.validate()
    event.enqueue()
    return {"message": "Story generator in progress! Check logs."}
