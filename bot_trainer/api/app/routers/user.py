from fastapi import APIRouter

from bot_trainer.api.auth import Authentication
from bot_trainer.api.processor import AccountProcessor
from bot_trainer.api.models import Response, User
from fastapi import Depends

router = APIRouter()
auth = Authentication()


@router.get("/details", response_model=Response)
async def get_users_details(current_user: User = Depends(auth.get_current_user)):
    """ This function returns the details of the current user """
    return {
        "data": {"user": AccountProcessor.get_complete_user_details(current_user.email)}
    }
