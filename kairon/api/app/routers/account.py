from fastapi import APIRouter, Depends
from fastapi import BackgroundTasks
from kairon.shared.auth import Authentication
from kairon.api.models import Response, RegisterAccount, TextData, Password, FeedbackRequest
from kairon.shared.models import User
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.utils import Utility

router = APIRouter()


@router.post("/registration", response_model=Response)
async def register_account(register_account: RegisterAccount, background_tasks: BackgroundTasks):
    """
    Registers a new account
    """
    user, mail, subject, body = await AccountProcessor.account_setup(register_account.dict(), "sysadmin")
    if Utility.email_conf["email"]["enable"]:
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


@router.post("/bot", response_model=Response)
async def add_bot(request: TextData, current_user: User = Depends(Authentication.get_current_user)):
    """
    Add new bot in a account.
    """
    AccountProcessor.add_bot(request.data, current_user.account, current_user.get_user())
    return {'message': 'Bot created'}


@router.get("/bot", response_model=Response)
async def list_bots(current_user: User = Depends(Authentication.get_current_user)):
    """
    List bots for account.
    """
    bots = list(AccountProcessor.list_bots(current_user.account))
    return Response(data=bots)


@router.put("/bot/{bot}", response_model=Response)
async def update_bot(bot: str, request: TextData, current_user: User = Depends(Authentication.get_current_user)):
    """
    Update name of the bot.
    """
    AccountProcessor.update_bot(request.data, bot)
    return {'message': 'Bot name updated'}


@router.delete("/bot/{bot}", response_model=Response)
async def delete_bot(bot: str, current_user: User = Depends(Authentication.get_current_user)):
    """
    Deletes bot.
    """
    AccountProcessor.delete_bot(bot, current_user.get_user())
    return {'message': 'Bot removed'}


@router.post("/feedback", response_model=Response)
async def feedback(request_data: FeedbackRequest, current_user: User = Depends(Authentication.get_current_user_and_bot)):
    """
    Receive feedback from user.
    """
    AccountProcessor.add_feedback(request_data.rating, current_user.get_user(), request_data.scale, request_data.feedback)
    return {"message": "Thanks for your feedback!"}
