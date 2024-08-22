from fastapi import APIRouter, Path, Security
from starlette.requests import Request

from kairon.shared.account.data_objects import Bot
from kairon.shared.authorization.processor import IntegrationProcessor
from kairon.shared.constants import ADMIN_ACCESS, TESTER_ACCESS, OWNER_ACCESS
from kairon.shared.data.constant import ACCESS_ROLES, ACTIVITY_STATUS
from kairon.shared.multilingual.utils.translator import Translator
from kairon.shared.utils import Utility, MailUtility
from kairon.shared.auth import Authentication
from kairon.shared.account.processor import AccountProcessor
from kairon.api.models import Response, BotAccessRequest, RecaptchaVerifiedTextData, RecaptchaVerifiedDictData
from kairon.shared.models import User
from fastapi import Depends
from fastapi import BackgroundTasks

router = APIRouter()


@router.get("/details", response_model=Response)
async def get_users_details(current_user: User = Depends(Authentication.get_current_user)):
    """
    returns the details of the current logged-in user
    """
    user_details = AccountProcessor.get_user_details_and_filter_bot_info_for_integration_user(
        current_user.email, current_user.is_integration_user, current_user.get_bot()
    )
    return {"data": {"user": user_details}}


@router.post("/details", response_model=Response)
async def update_users_details(current_user: User = Depends(Authentication.get_current_user)):
    """
    Updates the details of the current logged-in user.
    """
    AccountProcessor.update_is_onboarded(current_user.email)
    return {"message": "Details updated!"}


@router.get("/roles/access", response_model=Response)
async def list_access_for_roles(current_user: User = Security(Authentication.get_current_user)):
    """
    Lists roles and what components they can have access to.
    """
    return Response(data=Utility.system_metadata["roles"])


@router.post("/demo", response_model=Response)
async def book_a_demo(
        background_tasks: BackgroundTasks, request: Request,
        form_data: RecaptchaVerifiedDictData
):
    """
    Books a Demo for the User
    """
    Utility.validate_recaptcha_response(form_data.recaptcha_response, request=request)
    support_mail = Utility.environment["support_mail"]
    background_tasks.add_task(MailUtility.format_and_send_mail, mail_type='book_a_demo', email=support_mail,
                              first_name=form_data.data['first_name'], request=request, **form_data.dict())
    return {"message": "Thank You for your interest in Kairon. We will reach out to you soon."}


@router.post("/{bot}/member", response_model=Response)
async def allow_bot_for_user(
        allow_bot: BotAccessRequest, background_tasks: BackgroundTasks,
        bot: str = Path(description="bot id", examples=["613f63e87a1d435607c3c183"]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Allows user to access a bot.
    """
    bot_name, url = AccountProcessor.allow_bot_and_generate_invite_url(bot, allow_bot.email,
                                                                       current_user.get_user(),
                                                                       current_user.account, allow_bot.role)
    if Utility.email_conf["email"]["enable"]:
        accessor_name = AccountProcessor.get_user(allow_bot.email, raise_error=False)
        accessor = "Buddy"
        if accessor_name:
            accessor = f"{accessor_name.get('first_name')} {accessor_name.get('last_name')}"
        background_tasks.add_task(MailUtility.format_and_send_mail, mail_type='add_member', email=allow_bot.email, url=url,
                                  first_name=f'{current_user.first_name} {current_user.last_name}',
                                  bot_name=bot_name, role=allow_bot.role.value, accessor_name=accessor)
        return Response(message='An invitation has been sent to the user')
    else:
        return {"message": "User added"}


@router.post("/{bot}/invite/accept", response_model=Response)
async def accept_bot_collaboration_invite_with_token_validation(
        background_tasks: BackgroundTasks,
        token: RecaptchaVerifiedTextData, bot: str = Path(description="bot id", examples=["613f63e87a1d435607c3c183"])
):
    """
    Accepts a bot collaboration invitation sent via mail.
    """
    bot_admin, bot_name, accessor_email, role = AccountProcessor.validate_request_and_accept_bot_access_invite(token.data, bot)
    accessor_name = AccountProcessor.get_user(accessor_email, raise_error=False)
    first_name = AccountProcessor.get_user(bot_admin, raise_error=False).get("first_name")
    if Utility.email_conf["email"]["enable"]:
        background_tasks.add_task(MailUtility.format_and_send_mail, mail_type='add_member_confirmation', email=bot_admin,
                                  first_name=first_name, accessor_email=accessor_email,
                                  bot_name=bot_name, role=role, accessor_name=f"{accessor_name.get('first_name')} {accessor_name.get('last_name')}")
    return {"message": "Invitation accepted"}


@router.post("/{bot}/member/invite/accept", response_model=Response)
async def accept_bot_collaboration_invite(
        background_tasks: BackgroundTasks,
        bot: str = Path(description="bot id", examples=["613f63e87a1d435607c3c183"]),
        current_user: User = Security(Authentication.get_current_user)
):
    """
    Accepts a bot collaboration invitation for logged in user.
    """
    bot_admin, bot_name, accessor_email, role = AccountProcessor.accept_bot_access_invite(bot, current_user.get_user())
    accessor_name = AccountProcessor.get_user(accessor_email, raise_error=False).get("first_name")
    first_name = AccountProcessor.get_user(bot_admin, raise_error=False).get("first_name")
    if Utility.email_conf["email"]["enable"]:
        background_tasks.add_task(MailUtility.format_and_send_mail, mail_type='add_member_confirmation', email=bot_admin,
                                  first_name=first_name, accessor_email=accessor_email, accessor_name=accessor_name,
                                  bot_name=bot_name, role=role)
    return {"message": "Invitation accepted"}


@router.put("/{bot}/member", response_model=Response)
async def update_bot_access_for_user(
        allow_bot: BotAccessRequest, background_tasks: BackgroundTasks,
        bot: str = Path(description="bot id", examples=["613f63e87a1d435607c3c183"]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Updates user's role or status.
    """
    bot_name, owner_email, owner_name, member_name = AccountProcessor.update_bot_access(
        bot, allow_bot.email, current_user.get_user(), allow_bot.role, allow_bot.activity_status
    )
    if Utility.email_conf["email"]["enable"]:
        background_tasks.add_task(MailUtility.format_and_send_mail, mail_type='update_role_member_mail',
                                  email=allow_bot.email, first_name=member_name,
                                  bot_name=bot_name, new_role=allow_bot.role, status=allow_bot.activity_status,
                                  member_name=member_name, modifier_name=f'{current_user.first_name} {current_user.last_name}')
        background_tasks.add_task(MailUtility.format_and_send_mail, mail_type='update_role_owner_mail', email=owner_email,
                                  member_email=allow_bot.email, bot_name=bot_name, new_role=allow_bot.role,
                                  first_name=f'{current_user.first_name} {current_user.last_name}',
                                  status=allow_bot.activity_status, owner_name=owner_name)
    return Response(message='User access updated')


@router.put("/{bot}/owner/change", response_model=Response)
async def transfer_ownership(
        request_data: RecaptchaVerifiedTextData, background_tasks: BackgroundTasks,
        bot: str = Path(description="bot id", examples=["613f63e87a1d435607c3c183"]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=OWNER_ACCESS)
):
    """
    Transfers ownership to provided user.
    """
    bot_name = AccountProcessor.transfer_ownership(current_user.account, bot, current_user.get_user(), request_data.data)
    accessor_name = AccountProcessor.get_user(request_data.data, raise_error=False)
    if Utility.email_conf["email"]["enable"]:
        background_tasks.add_task(MailUtility.format_and_send_mail, mail_type='update_role_member_mail',
                                  email=request_data.data, bot_name=bot_name, new_role=ACCESS_ROLES.OWNER.value,
                                  first_name=f"{accessor_name.get('first_name')} {accessor_name.get('last_name')}",
                                  status=ACTIVITY_STATUS.ACTIVE.value, modifier_name=f'{current_user.first_name} {current_user.last_name}')
        background_tasks.add_task(MailUtility.format_and_send_mail, mail_type='transfer_ownership_mail',
                                  email=current_user.get_user(), new_owner_mail=request_data.data,
                                  bot_name=bot_name, new_role=ACCESS_ROLES.OWNER.value,
                                  first_name=f'{current_user.first_name} {current_user.last_name}')
    return Response(message='Ownership transferred')


@router.delete("/{bot}/member/{user}", response_model=Response)
async def remove_member_from_bot(
        user: str = Path(description="user mail id", examples=["user@kairon.ai"]),
        bot: str = Path(description="bot id", examples=["613f63e87a1d435607c3c183"]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Removes user from accessing the bot.
    """
    AccountProcessor.remove_member(bot, accessor_email=user, current_user=current_user.email)
    return Response(message='User removed')


@router.get("/{bot}/member", response_model=Response)
async def list_users_for_bot(
        bot: str = Path(description="bot id", examples=["613f63e87a1d435607c3c183"]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Lists active/inactive/invited users of a bot.
    """
    return Response(data=list(AccountProcessor.list_bot_accessors(bot)))


@router.get("/invites/active", response_model=Response)
async def list_active_bot_invites(current_user: User = Security(Authentication.get_current_user)):
    """
    Lists active bot invites.
    """
    return Response(data={'active_invites': list(AccountProcessor.list_active_invites(current_user.get_user()))})


@router.post("/search", response_model=Response)
async def search_user(
        request_data: RecaptchaVerifiedTextData, current_user: User = Security(Authentication.get_current_user)
):
    """
    Lists active bot invites.
    """
    return Response(data={'matching_users': list(AccountProcessor.search_user(request_data.data))})


@router.get("/auditlog/data", response_model=Response)
async def get_auditlog_for_user(
        current_user: User = Security(Authentication.get_current_user), start_idx: int = 0, page_size: int = 10
):
    """
    Get user specific auditlog .
    """
    return Response(data=AccountProcessor.get_auditlog_for_user(current_user.get_user(), start_idx, page_size))


@router.get("/multilingual/languages", response_model=Response)
async def get_supported_languages(current_user: User = Security(Authentication.get_current_user)):
    """
    Get supported languages for translation
    """
    return Response(data=Translator.get_supported_languages())


@router.get("/test/accuracy",response_model=Response)
async def get_model_testing_logs_accuracy(
        current_user: User = Security(Authentication.get_current_user, scopes=TESTER_ACCESS)
):
    """
    Fetches all logs with accuracy
    """

    data = AccountProcessor.get_model_testing_accuracy_of_all_accessible_bots(
        account_id=current_user.account, email=current_user.email)
    return Response(data=data)


@router.delete("/{bot}/leave", response_model=Response)
async def leave_bot(
    background_tasks: BackgroundTasks,
    bot: str = Path(description="bot id", examples=["613f63e87a1d435607c3c183"]),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Allows a user except owner to leave a bot.
    """
    result = await AccountProcessor.process_leave_bot(bot, current_user, current_user.bot_account)

    bot_data = result.get("bot_data")
    owner_info = result.get("owner_info")
    from kairon.shared.account.data_objects import User as User_data_object

    if Utility.email_conf["email"]["enable"]:
        bot_name = bot_data["name"]
        owner_email = owner_info["accessor_email"]
        owner_info_name = User_data_object.objects(email=owner_email).first()
        if owner_info_name:
            owner_name = f'{owner_info_name["first_name"].capitalize()} {owner_info_name["last_name"].capitalize()}'
        user_name = f'{current_user.first_name} {current_user.last_name}'

        # Notify the owner of the bot
        background_tasks.add_task(
            MailUtility.format_and_send_mail,
            mail_type='member_left_bot',
            email=owner_email,
            first_name=owner_name,
            user_name=user_name,
            bot_name=bot_name
        )

    return Response(message='Successfully left the bot')