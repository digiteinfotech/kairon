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

    :param register_account: The dictionary which consists of details of the new user
    :return: A message saying that the account is registered
    """
    await AccountProcessor.account_setup(register_account.dict(), "sysadmin")
    return {
        "message": "Account Registered! A confirmation link has been sent to your mail"
    }

@router.post("/email/confirmation", response_model=Response)
async def verify(token: TextData):
    """
    Used to verify an account after the user has clicked the verification link in their mail

    :param token: the unique token which consists of the embedded mail id of the user
    :return: A message saying that the account is verified
    """
    token_data = token.data
    await AccountProcessor.confirm_email(token_data)
    return {"message": "Account Verified!"}

@router.post("/password/reset", response_model=Response)
async def password_reset(mail: TextData):
    """
    Used to send a password reset link when the user clicks on the "Forgot Password" link and enters his/her mail id

    :param mail: mail id of the user
    :return: A message saying that a password reset link has been sent to the mail id
    """
    email = mail.data
    await AccountProcessor.send_reset_link(email.strip())
    return {"message": "Success! A password reset link has been sent to your mail id"}

@router.post("/password/change", response_model=Response)
async def password_changed(data: Password):
    """
    Used to overwrite the account's password after the user has changed his/her password with a new one

    :param data: Dictionary consisting of the email id of the user and the new password
    :return: A message saying that the password has been changed
    """
    await AccountProcessor.overwrite_password(data.data,data.password.get_secret_value())
    return {"message": "Success! Your password has been changed"}

@router.post("/email/confirmation/link", response_model=Response)
async def send_confirm_link(email: TextData):
    """
    Used to send the account verification link to the mail id of the user

    :param email: the mail id of the user
    :return: A message saying that the verification link has been sent to the mail id of the user
    """
    email = email.data
    await AccountProcessor.send_confirmation_link(email)
    return {"message": "Success! Confirmation link sent"}