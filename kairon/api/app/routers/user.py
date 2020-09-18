from fastapi import APIRouter

from kairon.api.auth import Authentication
from kairon.api.processor import AccountProcessor
from kairon.api.models import Response, User
from fastapi import Depends

router = APIRouter()
auth = Authentication()


@router.get("/details", response_model=Response)
async def get_users_details(current_user: User = Depends(auth.get_current_user)):
    """
    returns the details of the current logged-in user
    """
    return {
        "data": {"user": AccountProcessor.get_complete_user_details(current_user.email)}
    }
