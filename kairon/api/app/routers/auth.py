from fastapi import APIRouter
from fastapi import Depends
from fastapi.security import OAuth2PasswordRequestForm

from kairon.api.auth import Authentication
from kairon.api.processor import IntegrationsProcessor
from kairon.api.models import Response, User, TextData

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


@router.post("/{bot}/integration/token", response_model=Response)
async def generate_integration_token(
    request: TextData,
    current_user: User = Depends(auth.get_current_user_and_bot),
):
    """
    Generates an access token for api integration
    """
    access_token = auth.generate_integration_token(
        name=request.data,
        bot=current_user.get_bot(), user=current_user.get_user()
    )
    return {
        "data": {"access_token": access_token, "token_type": "bearer"},
        "message": f"""Please copy this token to a safe location.
        It will not be shown again.""",
    }


@router.get("/{bot}/integration/token", response_model=Response)
async def list_integration_tokens(
    current_user: User = Depends(auth.get_current_user_and_bot),
):
    """
    Lists all the integrations for the bot.
    """
    integrations = list(IntegrationsProcessor.get_integrations(current_user.get_bot()))
    return {
        "data": integrations
    }


@router.put("/{bot}/integration/token/{token_name}", response_model=Response)
async def update_integration_token_status(
    token_name: str,
    request: TextData,
    current_user: User = Depends(auth.get_current_user_and_bot),
):
    """
    Updates status of an integration token to one of : active, inactive, deleted.
    Status cannot be set to active or inactive once deleted.
    """
    IntegrationsProcessor.update_integrations(token_name, request.data, current_user.get_bot())
    return {
        "message": "Status updated",
    }
