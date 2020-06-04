from fastapi import APIRouter
from fastapi import Depends
from fastapi.security import OAuth2PasswordRequestForm

from bot_trainer.api.auth import Authentication
from bot_trainer.api.models import Response, User

router = APIRouter()
auth = Authentication()


@router.post("/login", response_model=Response)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """ This function accepts the Request Form data and generates an access token only if
        the user name and password are authenticated """
    access_token = auth.authenticate(form_data.username, form_data.password)
    return {
        "data": {"access_token": access_token, "token_type": "bearer"},
        "message": "User Authenticated",
    }


@router.get("/integration/token", response_model=Response)
async def generate_integration_token(
    current_user: User = Depends(auth.get_current_user),
):
    """ This function generates an access token to integrate the bot
        with other external services/architectures """
    access_token = auth.generate_integration_token(
        bot=current_user.bot, account=current_user.account
    )
    return {
        "data": {"access_token": access_token, "token_type": "bearer"},
        "message": """It is your responsibility to keep the token secret.
        If leaked then other may have access to your system.""",
    }
