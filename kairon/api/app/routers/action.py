from fastapi import APIRouter, Path, Security
from kairon.shared.auth import Authentication
from kairon.api.models import (
    Response,
    HttpActionConfigRequest, SlotSetActionRequest, EmailActionRequest, GoogleSearchActionRequest, JiraActionRequest,
    ZendeskActionRequest
)
from kairon.shared.constants import TESTER_ACCESS, DESIGNER_ACCESS
from kairon.shared.models import User
from kairon.shared.data.processor import MongoProcessor

router = APIRouter()
mongo_processor = MongoProcessor()


@router.post("/httpaction", response_model=Response)
async def add_http_action(
        request_data: HttpActionConfigRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Stores the http action config and story event
    """
    http_config_id = mongo_processor.add_http_action_config(request_data.dict(), current_user.get_user(),
                                                            current_user.get_bot())
    response = {"http_config_id": http_config_id}
    message = "Http action added!"
    return Response(data=response, message=message)


@router.get("/httpaction/{action}", response_model=Response)
async def get_http_action(action: str = Path(default=None, description="action name", example="http_action"),
                          current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Returns configuration set for the HTTP action
    """
    http_action_config = mongo_processor.get_http_action_config(action_name=action, bot=current_user.get_bot())
    return Response(data=http_action_config)


@router.get("/httpaction", response_model=Response)
async def list_http_actions(current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Returns list of http actions for bot.
    """
    actions = mongo_processor.list_http_actions(bot=current_user.get_bot())
    return Response(data=actions)


@router.put("/httpaction", response_model=Response)
async def update_http_action(
        request_data: HttpActionConfigRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Updates the http action config and related story event
    """
    http_config_id = mongo_processor.update_http_config(request_data=request_data, user=current_user.get_user(),
                                                        bot=current_user.get_bot())
    response = {"http_config_id": http_config_id}
    message = "Http action updated!"
    return Response(data=response, message=message)


@router.delete("/httpaction/{action}", response_model=Response)
async def delete_http_action(
        action: str = Path(default=None, description="action name", example="http_action"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Deletes the http action config and story event
    """
    mongo_processor.delete_action(action, user=current_user.get_user(), bot=current_user.get_bot())
    return Response(message="HTTP action deleted")


@router.post("/jira", response_model=Response)
async def add_jira_action(
        request_data: JiraActionRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Stores Jira action config.
    """
    mongo_processor.add_jira_action(request_data.dict(), current_user.get_bot(), current_user.get_user())
    return Response(message='Action added')


@router.get("/jira", response_model=Response)
async def list_jira_actions(current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Returns list of Jira actions for bot.
    """
    actions = list(mongo_processor.list_jira_actions(current_user.get_bot()))
    return Response(data=actions)


@router.put("/jira", response_model=Response)
async def edit_jira_action(
        request_data: JiraActionRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Edits the Jira action config.
    """
    mongo_processor.edit_jira_action(request_data.dict(), current_user.get_bot(), current_user.get_user())
    return Response(message='Action updated')


@router.delete("/jira/{action}", response_model=Response)
async def delete_jira_action(
        action: str = Path(default=None, description="action name", example="action_email"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Deletes the Jira action config.
    """
    mongo_processor.delete_action(action, current_user.get_bot(), current_user.get_user())
    return Response(message='Action deleted')


@router.post("/slotset", response_model=Response)
async def add_slot_set_action(
        request_data: SlotSetActionRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Stores the slot set action config.
    """
    mongo_processor.add_slot_set_action(request_data.dict(), current_user.get_bot(), current_user.get_user())
    return Response(message='Action added')


@router.get("/slotset", response_model=Response)
async def list_slot_set_actions(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Returns list of slot set actions for bot.
    """
    actions = mongo_processor.list_slot_set_actions(current_user.get_bot())
    return Response(data=actions)


@router.put("/slotset", response_model=Response)
async def edit_slot_set_action(
        request_data: SlotSetActionRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Edits the slot set action config.
    """
    mongo_processor.edit_slot_set_action(request_data.dict(), current_user.get_bot(), current_user.get_user())
    return Response(message='Action updated')


@router.delete("/slotset/{action}", response_model=Response)
async def delete_slot_set_action(
        action: str = Path(default=None, description="action name", example="action_reset_slot"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)):
    """
    Deletes the slot set action config.
    """
    mongo_processor.delete_action(action, current_user.get_bot(), current_user.get_user())
    return Response(message='Action deleted')


@router.post("/googlesearch", response_model=Response)
async def add_google_search_action(
        request_data: GoogleSearchActionRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Stores the google search action config.
    """
    action_id = mongo_processor.add_google_search_action(
        request_data.dict(), current_user.get_bot(), current_user.get_user()
    )
    return Response(data=action_id, message='Action added')


@router.get("/googlesearch", response_model=Response)
async def list_google_search_actions(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Returns list of google search actions for bot.
    """
    actions = list(mongo_processor.list_google_search_actions(bot=current_user.get_bot()))
    return Response(data=actions)


@router.put("/googlesearch", response_model=Response)
async def update_google_search_action(
        request_data: GoogleSearchActionRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Updates the google search action configuration.
    """
    mongo_processor.edit_google_search_action(
        request_data.dict(), current_user.get_bot(), current_user.get_user()
    )
    return Response(message='Action updated')


@router.delete("/googlesearch/{action}", response_model=Response)
async def delete_google_search_action(
        action: str = Path(default=None, description="action name", example="action_google_search"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Deletes the google search action.
    """
    mongo_processor.delete_action(action, user=current_user.get_user(), bot=current_user.get_bot())
    return Response(message="Action deleted")


@router.post("/email", response_model=Response)
async def add_email_action(
        request_data: EmailActionRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Stores the email action config.
    """
    mongo_processor.add_email_action(request_data.dict(), current_user.get_bot(), current_user.get_user())
    return Response(message='Action added')


@router.get("/email", response_model=Response)
async def list_email_actions(current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Returns list of email actions for bot.
    """
    actions = list(mongo_processor.list_email_action(current_user.get_bot()))
    return Response(data=actions)


@router.put("/email", response_model=Response)
async def edit_email_action(
        request_data: EmailActionRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Edits the email action config.
    """
    mongo_processor.edit_email_action(request_data.dict(), current_user.get_bot(), current_user.get_user())
    return Response(message='Action updated')


@router.delete("/email/{action}", response_model=Response)
async def delete_email_action(
        action: str = Path(default=None, description="action name", example="action_email"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)):
    """
    Deletes the email action config.
    """
    mongo_processor.delete_action(action, current_user.get_bot(), current_user.get_user())
    return Response(message='Action deleted')


@router.post("/zendesk", response_model=Response)
async def add_zendesk_action(
        request_data: ZendeskActionRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Stores the email action config.
    """
    mongo_processor.add_zendesk_action(request_data.dict(), current_user.get_bot(), current_user.get_user())
    return Response(message='Action added')


@router.get("/zendesk", response_model=Response)
async def list_zendesk_actions(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Returns list of email actions for bot.
    """
    actions = list(mongo_processor.list_zendesk_actions(current_user.get_bot()))
    return Response(data=actions)


@router.put("/zendesk", response_model=Response)
async def edit_zendesk_action(
        request_data: ZendeskActionRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Edits the email action config.
    """
    mongo_processor.edit_zendesk_action(request_data.dict(), current_user.get_bot(), current_user.get_user())
    return Response(message='Action updated')


@router.delete("/zendesk/{action}", response_model=Response)
async def delete_zendesk_action(
        action: str = Path(default=None, description="action name", example="action_email"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Deletes the email action config.
    """
    mongo_processor.delete_action(action, current_user.get_bot(), current_user.get_user())
    return Response(message='Action deleted')
