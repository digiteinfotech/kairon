from kairon.events.definitions.data_generation import DataGenerationEvent
from kairon.shared.models import User
from fastapi import APIRouter, Security
from kairon.shared.auth import Authentication
from kairon.api.models import Response
from kairon.shared.constants import DESIGNER_ACCESS

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
