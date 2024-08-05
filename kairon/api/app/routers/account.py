from fastapi import APIRouter, Depends, Security, Form, Path
from fastapi import BackgroundTasks
from starlette.requests import Request

from kairon.shared.auth import Authentication
from kairon.api.models import Response, RegisterAccount, TextData, Password, FeedbackRequest, DictData, \
    RecaptchaVerifiedTextData, AddBotRequest
from kairon.shared.constants import OWNER_ACCESS
from kairon.shared.models import User
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.organization.processor import OrgProcessor
from kairon.shared.utils import Utility, MailUtility

router = APIRouter()


@router.post("/registration", response_model=Response)
async def register_account(register_account: RegisterAccount, background_tasks: BackgroundTasks, request: Request):
    """
    Registers a new account
    """
    Utility.validate_enable_sso_only()
    user, mail, url = await AccountProcessor.account_setup(register_account.dict())
    AccountProcessor.get_location_and_add_trusted_device(user['email'], register_account.fingerprint, request, False)
    if Utility.email_conf["email"]["enable"]:
        background_tasks.add_task(MailUtility.format_and_send_mail, mail_type='verification', email=mail, first_name=user['first_name'], url=url)
        return {"message": "Account Registered! A confirmation link has been sent to your mail"}
    else:
        return {"message": "Account Registered!"}


@router.post("/device/trusted", response_model=Response)
async def add_trusted_device(
        background_tasks: BackgroundTasks, request: Request, fingerprint: TextData,
        current_user: User = Depends(Authentication.get_current_user)
):
    """
    Add a device as trusted device.
    """
    url, geo_location = AccountProcessor.get_location_and_add_trusted_device(current_user.email, fingerprint.data, request, raise_err=True)
    if Utility.email_conf["email"]["enable"]:
        background_tasks.add_task(
            MailUtility.format_and_send_mail, mail_type='add_trusted_device', email=current_user.email,
            first_name=current_user.first_name, url=url, **geo_location
        )
        return {"message": "A confirmation link has been sent to your registered mail address"}
    else:
        return {"message": "Trusted device added!"}


@router.post("/device/trusted/verify", response_model=Response)
async def is_trusted_device(fingerprint: TextData, current_user: User = Depends(Authentication.get_current_user)):
    """
    Verifies whether device is trusted.
    """
    return Response(data={
        "is_trusted_device": fingerprint.data in AccountProcessor.list_trusted_device_fingerprints(current_user.email)
    })


@router.post("/device/trusted/confirm", response_model=Response)
async def confirm_add_trusted_device(token: RecaptchaVerifiedTextData):
    """
    Confirm addition of device as trusted device.
    """
    decoded_jwt = Utility.decode_limited_access_token(token.data)
    AccountProcessor.confirm_add_trusted_device(decoded_jwt.get('mail_id'), decoded_jwt.get('fingerprint'))
    return {"message": "Trusted device added!"}


@router.get("/device/trusted", response_model=Response)
async def list_trusted_device(current_user: User = Depends(Authentication.get_current_user)):
    """
    List trusted devices.
    """
    return Response(data={"trusted_devices": list(AccountProcessor.list_trusted_devices(current_user.email))})


@router.delete("/device/trusted/{fingerprint}", response_model=Response)
async def remove_trusted_device(fingerprint: str, current_user: User = Depends(Authentication.get_current_user)):
    """
    Removes trusted device.
    """
    AccountProcessor.remove_trusted_device(current_user.email, fingerprint)
    return {"message": "Trusted device removed!"}


@router.post("/email/confirmation", response_model=Response)
async def verify(token: RecaptchaVerifiedTextData, background_tasks: BackgroundTasks):
    """
    Used to verify an account after the user has clicked the verification link in their mail
    """
    Utility.validate_enable_sso_only()
    token_data = token.data
    mail, first_name = await AccountProcessor.confirm_email(token_data)
    background_tasks.add_task(MailUtility.format_and_send_mail, mail_type='verification_confirmation', email=mail, first_name=first_name)
    return {"message": "Account Verified!"}


@router.post("/password/reset", response_model=Response)
async def password_link_generate(mail: RecaptchaVerifiedTextData, background_tasks: BackgroundTasks):
    """
    Used to send a password reset link when the user clicks on the "Forgot Password" link and enters his/her mail id
    """
    Utility.validate_enable_sso_only()
    email = mail.data
    mail, first_name, url = await AccountProcessor.send_reset_link(email.strip())
    background_tasks.add_task(MailUtility.format_and_send_mail, mail_type='password_reset', email=mail, first_name=first_name, url=url)
    return {"message": "Success! A password reset link has been sent to your mail id"}


@router.post("/password/change", response_model=Response)
async def password_change(data: Password, background_tasks: BackgroundTasks):
    """
    Used to overwrite the account's password after the user has changed his/her password with a new one
    """
    Utility.validate_enable_sso_only()
    mail, first_name = await AccountProcessor.overwrite_password(data.data, data.password.get_secret_value())
    background_tasks.add_task(MailUtility.format_and_send_mail, mail_type='password_reset_confirmation', email=mail, first_name=first_name)
    return {"message": "Success! Your password has been changed"}


@router.post("/email/confirmation/link", response_model=Response)
async def send_confirm_link(email: RecaptchaVerifiedTextData, background_tasks: BackgroundTasks):
    """
    Used to send the account verification link to the mail id of the user
    """
    Utility.validate_enable_sso_only()
    email = email.data
    mail, first_name, url = await AccountProcessor.send_confirmation_link(email)
    background_tasks.add_task(MailUtility.format_and_send_mail, mail_type='verification', email=mail, first_name=first_name, url=url)
    return {"message": "Success! Confirmation link sent"}


@router.post("/bot", response_model=Response)
async def add_bot(request: AddBotRequest, background_tasks: BackgroundTasks,
                  current_user: User = Depends(Authentication.get_current_user)):
    """
    Add new bot in an account.
    """
    bot_id = await AccountProcessor.add_bot_with_template(request.name, current_user.account, current_user.get_user(),
                                                          template_name=request.from_template)
    if not Utility.check_empty_string(request.from_template):
        background_tasks.add_task(Utility.reload_model, bot_id, current_user.email)
    return Response(data={"bot_id": bot_id}, message="Bot created")


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
    AccountProcessor.delete_bot(bot, current_user.get_user())
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
    AccountProcessor.delete_account(current_user.account, current_user.get_user())
    return {"message": "Account deleted"}


@router.post("/organization", response_model=Response)
async def add_organization(request_data: DictData,
                           current_user: User = Depends(Authentication.get_current_user)
                           ):
    """
    Add organization.
    """
    org_id = OrgProcessor.upsert_organization(current_user, request_data.data)
    return Response(data={"org_id": org_id}, message="organization added")


@router.get("/organization", response_model=Response)
async def get_organization(current_user: User = Depends(Authentication.get_current_user)):
    """
    Get organization.
    """
    data = OrgProcessor.get_organization_for_account(current_user.account)
    return Response(data=data)


@router.delete("/organization/{org_id}", response_model=Response)
async def delete_organization(org_id: str, current_user: User = Depends(Authentication.get_current_user)):
    """
    Delete organization.
    """
    OrgProcessor.delete_org(current_user.account, org_id, user=current_user.get_user())
    return Response(message="Organization deleted")
