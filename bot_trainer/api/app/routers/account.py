from fastapi import APIRouter

from bot_trainer.api.auth import Authentication
from bot_trainer.api.models import Response, RegisterAccount, TextData, Password
from bot_trainer.api.processor import AccountProcessor

router = APIRouter()
auth = Authentication()


@router.post("/registration", response_model=Response)
async def register_account(register_account: RegisterAccount):
    """
    Registers a new account
    """
    await AccountProcessor.account_setup(register_account.dict(), "sysadmin")
    return {
        "message": "Account Registered! A confirmation link has been sent to your mail"
    }

@router.post("/email/confirmation", response_model=Response)
async def verify(token: TextData):
    """
    Used to verify an account after the user has clicked the verification link in their mail
    """
    token_data = token.data
    await AccountProcessor.confirm_email(token_data)
    return {"message": "Account Verified!"}

@router.post("/password/reset", response_model=Response)
async def password_link_generate(mail: TextData):
    """
    Used to send a password reset link when the user clicks on the "Forgot Password" link and enters his/her mail id
    """
    email = mail.data
    await AccountProcessor.send_reset_link(email.strip())
    return {"message": "Success! A password reset link has been sent to your mail id"}

@router.post("/password/change", response_model=Response)
async def password_change(data: Password):
    """
    Used to overwrite the account's password after the user has changed his/her password with a new one
    """
    await AccountProcessor.overwrite_password(data.data,data.password.get_secret_value())
    return {"message": "Success! Your password has been changed"}

@router.post("/email/confirmation/link", response_model=Response)
async def send_confirm_link(email: TextData):
    """
    Used to send the account verification link to the mail id of the user
    """
    email = email.data
    await AccountProcessor.send_confirmation_link(email)
    return {"message": "Success! Confirmation link sent"}
