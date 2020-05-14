import requests
from fastapi import APIRouter
from fastapi import Depends

from bot_trainer.api.auth import Authentication
from bot_trainer.api.models import (Response, User, ListData)
from bot_trainer.utils import Utility

router = APIRouter()
auth = Authentication()


@router.post("/questions", response_model=Response)
async def questions(
    request_data: ListData, current_user: User = Depends(auth.get_current_user)
):
    response = requests.post(
        Utility.environment["augmentation_url"], json=request_data.data
    )
    return response.json()
