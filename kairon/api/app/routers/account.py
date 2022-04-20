from fastapi import APIRouter, Depends, Security
from fastapi import BackgroundTasks
from kairon.shared.auth import Authentication
from kairon.api.models import Response, RegisterAccount, TextData, Password, FeedbackRequest, DictData
from kairon.shared.constants import OWNER_ACCESS
from kairon.shared.models import User
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.utils import Utility

router = APIRouter()


@router.post("/registration", response_model=Response)
async def register_account(register_account: RegisterAccount, background_tasks: BackgroundTasks):
    """
    Registers a new account
    """
    user, mail, url = await AccountProcessor.account_setup(register_account.dict())
    if Utility.email_conf["email"]["enable"]:
        background_tasks.add_task(Utility.format_and_send_mail, mail_type='verification', email=mail, first_name=user['first_name'], url=url)
        return {"message": "Account Registered! A confirmation link has been sent to your mail"}
    else:
        return {"message": "Account Registered!"}


@router.post("/email/confirmation", response_model=Response)
async def verify(token: TextData, background_tasks: BackgroundTasks):
    """
    Used to verify an account after the user has clicked the verification link in their mail
    """
    token_data = token.data
    mail, first_name = await AccountProcessor.confirm_email(token_data)
    background_tasks.add_task(Utility.format_and_send_mail, mail_type='verification_confirmation', email=mail, first_name=first_name)
    return {"message": "Account Verified!"}


@router.post("/password/reset", response_model=Response)
async def password_link_generate(mail: TextData, background_tasks: BackgroundTasks):
    """
    Used to send a password reset link when the user clicks on the "Forgot Password" link and enters his/her mail id
    """
    email = mail.data
    mail, first_name, url = await AccountProcessor.send_reset_link(email.strip())
    background_tasks.add_task(Utility.format_and_send_mail, mail_type='password_reset', email=mail, first_name=first_name, url=url)
    return {"message": "Success! A password reset link has been sent to your mail id"}


@router.post("/password/change", response_model=Response)
async def password_change(data: Password, background_tasks: BackgroundTasks):
    """
    Used to overwrite the account's password after the user has changed his/her password with a new one
    """
    mail, first_name = await AccountProcessor.overwrite_password(data.data, data.password.get_secret_value())
    background_tasks.add_task(Utility.format_and_send_mail, mail_type='password_reset_confirmation', email=mail, first_name=first_name)
    return {"message": "Success! Your password has been changed"}


@router.post("/email/confirmation/link", response_model=Response)
async def send_confirm_link(email: TextData, background_tasks: BackgroundTasks):
    """
    Used to send the account verification link to the mail id of the user
    """
    email = email.data
    mail, first_name, url = await AccountProcessor.send_confirmation_link(email)
    background_tasks.add_task(Utility.format_and_send_mail, mail_type='verification', email=mail, first_name=first_name, url=url)
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
    bots = AccountProcessor.get_accessible_bot_details(current_user.account, current_user.email)
    if current_user.is_integration_user:
        bots = Utility.filter_bot_details_for_integration_user(current_user.get_bot(), bots)
    return Response(data=bots)


@router.put("/bot/{bot}", response_model=Response)
async def update_bot(
        bot: str, request: TextData,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=OWNER_ACCESS)
):
    """
    Update name of the bot.
    """
    AccountProcessor.update_bot(request.data, bot)
    return {'message': 'Name updated'}


@router.delete("/bot/{bot}", response_model=Response)
async def delete_bot(
        bot: str, current_user: User = Security(Authentication.get_current_user_and_bot, scopes=OWNER_ACCESS)):
    """
    Deletes bot.
    """
    AccountProcessor.delete_bot(bot)
    return {'message': 'Bot removed'}


@router.post("/feedback", response_model=Response)
async def feedback(request_data: FeedbackRequest, current_user: User = Depends(Authentication.get_current_user)):
    """
    Receive feedback from user.
    """
    AccountProcessor.add_feedback(request_data.rating, current_user.get_user(), request_data.scale, request_data.feedback)
    return {"message": "Thanks for your feedback!"}


@router.put("/config/ui", response_model=Response)
async def update_ui_config(request_data: DictData, current_user: User = Depends(Authentication.get_current_user)):
    """
    Add/update ui configuration for user.
    """
    AccountProcessor.update_ui_config(request_data.data, current_user.get_user())
    return {"message": "Config saved!"}


@router.get("/config/ui", response_model=Response)
async def get_ui_config(current_user: User = Depends(Authentication.get_current_user)):
    """
    Get ui configuration for user.
    """
    return {'data': AccountProcessor.get_ui_config(current_user.get_user())}


@router.delete("/delete", response_model=Response)
async def delete_account(current_user: User = Depends(Authentication.get_current_user)):
    """
    Deletes user account.
    """
    AccountProcessor.delete_account(current_user.account)
    return {"message": "Account deleted"}
