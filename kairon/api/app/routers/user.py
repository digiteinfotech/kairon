from fastapi import APIRouter, Path, Security

from kairon.shared.constants import ADMIN_ACCESS, TESTER_ACCESS
from kairon.shared.utils import Utility
from kairon.shared.auth import Authentication
from kairon.shared.account.processor import AccountProcessor
from kairon.api.models import Response, BotAccessRequest, TextData
from kairon.shared.models import User
from fastapi import Depends
from fastapi import BackgroundTasks

router = APIRouter()


@router.get("/details", response_model=Response)
async def get_users_details(current_user: User = Depends(Authentication.get_current_user)):
    """
    returns the details of the current logged-in user
    """
    return {
        "data": {"user": AccountProcessor.get_complete_user_details(current_user.email)}
    }


@router.post("/{bot}/member", response_model=Response)
async def allow_bot_for_user(allow_bot: BotAccessRequest, background_tasks: BackgroundTasks,
                             bot: str = Path(default=None, description="bot id", example="613f63e87a1d435607c3c183"),
                             current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)):
    """
    Allows user to access a bot.
    """
    bot_name, url = AccountProcessor.allow_bot_and_generate_invite_url(bot, allow_bot.email,
                                                                       current_user.get_user(),
                                                                       current_user.account, allow_bot.role)
    if Utility.email_conf["email"]["enable"]:
        background_tasks.add_task(Utility.format_and_send_mail, mail_type='add_member', email=allow_bot.email, url=url,
                                  first_name=f'{current_user.first_name} {current_user.last_name}',
                                  bot_name=bot_name, role=allow_bot.role)
        return Response(message='An invitation has been sent to the user')
    else:
        return {"message": "User added"}


@router.post("/{bot}/member/invite/accept", response_model=Response)
async def accept_bot_collaboration_invite(
        background_tasks: BackgroundTasks,
        token: TextData, bot: str = Path(default=None, description="bot id", example="613f63e87a1d435607c3c183")
):
    """
    Accepts a bot collaboration invitation.
    """
    bot_admin, bot_name, accessor_email, role = AccountProcessor.accept_bot_access_invite(token.data, bot)
    if Utility.email_conf["email"]["enable"]:
        background_tasks.add_task(Utility.format_and_send_mail, mail_type='add_member_confirmation', email=bot_admin,
                                  first_name=bot_admin,
                                  bot_name=bot_name, role=role)
    return {"message": "Invitation accepted"}


@router.put("/{bot}/member", response_model=Response)
async def update_bot_access_for_user(allow_bot: BotAccessRequest,
                                     bot: str = Path(default=None, description="bot id", example="613f63e87a1d435607c3c183"),
                                     current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)):
    """
    Updates user's role or status.
    """
    AccountProcessor.update_bot_access(bot, allow_bot.email,
                                       current_user.get_user(),
                                       allow_bot.role, allow_bot.activity_status)
    return Response(message='User access updated')


@router.delete("/{bot}/member/{user}", response_model=Response)
async def remove_user_from_bot(
        user: str = Path(default=None, description="user mail id", example="user@kairon.ai"),
        bot: str = Path(default=None, description="bot id", example="613f63e87a1d435607c3c183"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Removes user from accessing the bot.
    """
    AccountProcessor.remove_bot_access(bot, accessor_email=user)
    return Response(message='User removed')


@router.get("/{bot}/member", response_model=Response)
async def list_users_for_bot(bot: str = Path(default=None, description="bot id", example="613f63e87a1d435607c3c183"),
                             current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Lists active/inactive/invited users of a bot.
    """
    return Response(data=list(AccountProcessor.list_bot_accessors(bot)))
