from fastapi import APIRouter

from bot_trainer.api.auth import Authentication
from bot_trainer.api.models import Response, RegisterAccount, TextData
from bot_trainer.api.processor import AccountProcessor

router = APIRouter()
auth = Authentication()


@router.post("/registration", response_model=Response)
async def register_account(register_account: RegisterAccount):
    """
    Register New Account
    """
    await AccountProcessor.account_setup(register_account.dict(), "sysadmin")
    return {
        "message": "Account Registered! A confirmation link has been sent to your mail"
    }


@router.post("/email/confirmation", response_model=Response)
async def verify(token: TextData):
    token_data = token.data
    await AccountProcessor.confirm_email(token_data)
    return {"message": "Account Confirmed!"}
