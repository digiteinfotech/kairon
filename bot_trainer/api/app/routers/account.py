from fastapi import APIRouter

from bot_trainer.api.auth import Authentication
from bot_trainer.api.processor import AccountProcessor
from bot_trainer.api.models import Response, RegisterAccount
from fastapi import Depends

router = APIRouter()
auth = Authentication()


@router.post("/registration", response_model=Response)
async def register_account(register_account: RegisterAccount):
    """new account registeration api"""
    AccountProcessor.account_setup(register_account.dict(), "sysadmin")
    return {"message": "Account Registered!"}
