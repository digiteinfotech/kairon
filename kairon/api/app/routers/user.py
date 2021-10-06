from fastapi import APIRouter

from kairon.shared.auth import Authentication
from kairon.shared.account.processor import AccountProcessor
from kairon.api.models import Response
from kairon.shared.models import User
from fastapi import Depends

router = APIRouter()


@router.get("/details", response_model=Response)
async def get_users_details(current_user: User = Depends(Authentication.get_current_user)):
    """
    returns the details of the current logged-in user
    """
    return {
        "data": {"user": AccountProcessor.get_complete_user_details(current_user.email)}
    }
