from fastapi import APIRouter
from fastapi import BackgroundTasks
from bot_trainer.api.auth import Authentication
from bot_trainer.api.models import Response, RegisterAccount, TextData, Password
from bot_trainer.api.processor import AccountProcessor
from bot_trainer.utils import Utility

router = APIRouter()
auth = Authentication()


@router.post("/registration", response_model=Response)
async def register_account(register_account: RegisterAccount, background_tasks: BackgroundTasks):
    """
    Registers a new account
    """
    user, mail, subject, body = await AccountProcessor.account_setup(register_account.dict(), "sysadmin")
    if AccountProcessor.EMAIL_ENABLED:
        background_tasks.add_task(Utility.validate_and_send_mail, email=mail, subject=subject, body=body)
        return {"message": "Account Registered! A confirmation link has been sent to your mail"}
    else:
        return {"message": "Account Registered!"}


@router.post("/email/confirmation", response_model=Response)
async def verify(token: TextData, background_tasks: BackgroundTasks):
    """
    Used to verify an account after the user has clicked the verification link in their mail
    """
    token_data = token.data
    mail, subject, body = await AccountProcessor.confirm_email(token_data)
    background_tasks.add_task(Utility.validate_and_send_mail, email=mail, subject=subject, body=body)
    return {"message": "Account Verified!"}


@router.post("/password/reset", response_model=Response)
async def password_link_generate(mail: TextData, background_tasks: BackgroundTasks):
    """
    Used to send a password reset link when the user clicks on the "Forgot Password" link and enters his/her mail id
    """
    email = mail.data
    mail, subject, body = await AccountProcessor.send_reset_link(email.strip())
    background_tasks.add_task(Utility.validate_and_send_mail, email=mail, subject=subject, body=body)
    return {"message": "Success! A password reset link has been sent to your mail id"}


@router.post("/password/change", response_model=Response)
async def password_change(data: Password, background_tasks: BackgroundTasks):
    """
    Used to overwrite the account's password after the user has changed his/her password with a new one
    """
    mail, subject, body = await AccountProcessor.overwrite_password(data.data,data.password.get_secret_value())
    background_tasks.add_task(Utility.validate_and_send_mail, email=mail, subject=subject, body=body)
    return {"message": "Success! Your password has been changed"}


@router.post("/email/confirmation/link", response_model=Response)
async def send_confirm_link(email: TextData, background_tasks: BackgroundTasks):
    """
    Used to send the account verification link to the mail id of the user
    """
    email = email.data
    mail, subject, body = await AccountProcessor.send_confirmation_link(email)
    background_tasks.add_task(Utility.validate_and_send_mail, email=mail, subject=subject, body=body)
    return {"message": "Success! Confirmation link sent"}
