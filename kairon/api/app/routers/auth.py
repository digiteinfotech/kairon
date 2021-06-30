from fastapi import APIRouter
from fastapi import Depends
from fastapi.security import OAuth2PasswordRequestForm

from kairon.api.auth import Authentication
from kairon.api.models import Response, User

router = APIRouter()
auth = Authentication()


@router.post("/login", response_model=Response)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticates the user and generates jwt token
    """
    access_token = auth.authenticate(form_data.username, form_data.password)
    return {
        "data": {"access_token": access_token, "token_type": "bearer"},
        "message": "User Authenticated",
    }


@router.get("/{bot}/integration/token", response_model=Response)
async def generate_integration_token(
    current_user: User = Depends(auth.get_current_user_and_bot),
):
    """
    Generates an access token for api integration
    """
    access_token = auth.generate_integration_token(
        bot=current_user.get_bot(), account=current_user.account
    )
    return {
        "data": {"access_token": access_token, "token_type": "bearer"},
        "message": """It is your responsibility to keep the token secret.
        If leaked then other may have access to your system.""",
    }
