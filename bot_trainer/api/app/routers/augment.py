import requests
from fastapi import APIRouter
from fastapi import Depends

from bot_trainer.api.auth import Authentication
from bot_trainer.api.models import Response, User, ListData
from bot_trainer.utils import Utility

router = APIRouter()
auth = Authentication()


@router.post("/questions", response_model=Response)
async def questions(
    request_data: ListData, current_user: User = Depends(auth.get_current_user)
):
    """
    Generates other similar text by augmenting original text
    """
    plain_text_data = [
        Utility.extract_text_and_entities(data)[0] for data in request_data.data
    ]
    response = requests.post(
        Utility.environment["augmentation"]["url"], json=plain_text_data
    )
    return response.json()
