from fastapi import APIRouter
from fastapi import Depends
from fastapi.security import OAuth2PasswordRequestForm

from bot_trainer.api.auth import Authentication
from bot_trainer.api.models import *

router = APIRouter()
auth = Authentication()


@router.post("/login", response_model=Response)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    access_token = auth.authenticate(form_data.username, form_data.password)
    return {
        "data": {"access_token": access_token, "token_type": "bearer"},
        "message": "User Authenticated",
    }
