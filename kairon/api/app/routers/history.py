import datetime
from typing import Text

from fastapi import APIRouter, Security
from fastapi import Query
from starlette.background import BackgroundTasks
from starlette.responses import StreamingResponse
from io import BytesIO

from kairon.api.models import Response
from kairon.events.events import EventsTrigger
from kairon.shared.auth import Authentication
from kairon.shared.constants import TESTER_ACCESS, ADMIN_ACCESS
from kairon.shared.data.history_log_processor import HistoryDeletionLogProcessor
from kairon.shared.models import User
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.utils import Utility
from kairon.shared.data.utils import DataUtility, ChatHistoryUtils

router = APIRouter()


@router.get("/users", response_model=Response)
async def chat_history_users(month: int = Query(default=1, ge=1, le=6), current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):

    """
    Fetches the list of user who has conversation with the agent
    """
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/conversations/users',
        {'month': month}
    )


@router.get("/users/{sender}", response_model=Response)
async def chat_history(
    sender: Text, month: int = Query(default=1, ge=1, le=6), current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the list of conversation with the agent by particular user
    """
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/conversations/users/{sender}',
        {'month': month}
    )


@router.get("/metrics/users", response_model=Response)
async def user_with_metrics(
        month: int = Query(default=1, ge=1, le=6), current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the list of user who has conversation with the agent with steps anf time
    """
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/users',
        {'month': month}
    )


@router.get("/metrics/fallback", response_model=Response)
async def visitor_hit_fallback(month: int = Query(default=1, ge=1, le=6), current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the number of times the agent hit a fallback (ie. not able to answer) to user queries
    """
    fallback_action, nlu_fallback_action = DataUtility.load_fallback_actions(current_user.get_bot())
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/fallback',
        {'month': month, 'action_fallback': fallback_action, 'nlu_fallback': nlu_fallback_action}
    )


@router.get("/metrics/conversation/steps", response_model=Response)
async def conversation_steps(month: int = Query(default=1, ge=1, le=6), current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
     Fetches the number of conversation steps that took place in the chat between the users and the agent
     """
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/conversation/steps',
        {'month': month}
    )


@router.get("/metrics/conversation/time", response_model=Response)
async def conversation_time(month: int = Query(default=1, ge=1, le=6),current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the duration of the chat that took place between the users and the agent"""
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/conversation/time',
        {'month': month}
    )


@router.get("/metrics/user/engaged", response_model=Response)
async def count_engaged_users(month: int = Query(default=1, ge=1, le=6), conversation_step_threshold: int = 10,
                              current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):

    """
    Fetches the number of engaged users of the bot
    """
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/users/engaged',
        {'month': month, 'conversation_step_threshold': conversation_step_threshold}
    )


@router.get("/metrics/user/new", response_model=Response)
async def count_new_users(month: int = Query(default=1, ge=1, le=6), current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the number of new users of the bot
    """
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/users/new',
        {'month': month}
    )


@router.get("/metrics/conversation/success", response_model=Response)
async def complete_conversations(month: int = Query(default=1, ge=1, le=6), current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the number of successful conversations of the bot, which had no fallback
    """
    fallback_action, nlu_fallback_action = DataUtility.load_fallback_actions(current_user.get_bot())
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/conversation/success',
        {'month': month, 'action_fallback': fallback_action, 'nlu_fallback': nlu_fallback_action}
    )


@router.get("/metrics/user/retention", response_model=Response)
async def calculate_retention(month: int = Query(default=1, ge=1, le=6), current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the user retention percentage of the bot
    """
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/users/retention',
        {'month': month}
    )


@router.get("/metrics/trend/user/engaged", response_model=Response)
async def engaged_users_trend(month: int = Query(default=6, ge=1, le=6),
                              conversation_step_threshold: int = 10,
                              current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):

    """
    Fetches the counts of engaged users of the bot for previous months
    """
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/trends/users/engaged',
        {'month': month, 'conversation_step_threshold': conversation_step_threshold}
    )


@router.get("/metrics/trend/user/new", response_model=Response)
async def new_users_trend(month: int = Query(default=6, ge=1, le=6), current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the counts of new users of the bot for previous months
    """
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/trends/users/new',
        {'month': month}
    )


@router.get("/metrics/trend/conversation/success", response_model=Response)
async def complete_conversation_trend(month: int = Query(default=6, ge=1, le=6), current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the counts of successful conversations of the bot for previous months
    """
    fallback_action, nlu_fallback_action = DataUtility.load_fallback_actions(current_user.get_bot())
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/trends/conversations/success',
        {'month': month, 'action_fallback': fallback_action, 'nlu_fallback': nlu_fallback_action}
    )


@router.get("/metrics/trend/user/retention", response_model=Response)
async def retention_trend(month: int = Query(default=6, ge=1, le=6), current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the counts of user retention percentages of the bot for previous months
    """
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/trends/users/retention',
        {'month': month}
    )


@router.get("/metrics/trend/user/fallback", response_model=Response)
async def fallback_trend(month: int = Query(default=6, ge=1, le=6), current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the fallback count of the bot for previous months
    """
    fallback_action, nlu_fallback_action = DataUtility.load_fallback_actions(current_user.get_bot())
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/trends/fallback',
        {'month': month, 'action_fallback': fallback_action, 'nlu_fallback': nlu_fallback_action}
    )


@router.get("/conversations", response_model=Response)
async def flat_conversations(month: int = Query(default=1, ge=1, le=6), current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the flattened conversation data of the bot for previous months
    """
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/conversations/',
        {'month': month}
    )


@router.get("/conversations/download")
async def download_conversations(
        month: int = Query(default=1, ge=1, le=6),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS),
):
    """
    Downloads conversation history of the bot, for the specified months
    """
    response = Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/conversations/download',
        {'month': month}, return_json=False
    )

    bot_name = [bot['name'] for bot in AccountProcessor.list_bots(current_user.account) if bot['_id'] == current_user.get_bot()][0]
    response.headers[
        "Content-Disposition"
    ] = f"attachment; filename=conversation_history_{bot_name}{datetime.date.today().strftime('_%d_%m_%y.csv')}"
    return StreamingResponse(BytesIO(response.content), headers=response.headers)


@router.get("/metrics/intents/topmost", response_model=Response)
async def top_n_intents(month: int = Query(default=1, ge=1, le=6), top_n: int = Query(default=10, ge=1),
                        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the top n identified intents of the bot
    """
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/intents/topmost',
        {'month': month, 'top_n': top_n}
    )


@router.get("/metrics/actions/topmost", response_model=Response)
async def top_n_actions(month: int = Query(default=1, ge=1, le=6), top_n: int = Query(default=10, ge=1),
                        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the top n identified actions of the bot
    """
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/actions/topmost',
        {'month': month, 'top_n': top_n}
    )


@router.get("/metrics/trend/conversations/total", response_model=Response)
async def total_conversation_trend(month: int = Query(default=6, ge=1, le=6), current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the counts of conversations of the bot for previous months
    """
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/trends/conversations/total',
        {'month': month}
    )


@router.get("/metrics/trend/conversations/steps", response_model=Response)
async def conversation_step_trend(month: int = Query(default=6, ge=1, le=6), current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the average conversation steps of the bot for previous months
    """
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/trends/conversations/steps',
        {'month': month}
    )


@router.get("/conversations/wordcloud")
async def word_cloud(
        month: int = Query(default=1, ge=1, le=6),
        l_bound: float = Query(default=0, ge=0, lt=1),
        u_bound: float = Query(default=1, gt=0, le=1),
        stopword_list: list = Query(default=None),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS),
):
    """
    Returns the conversation string that is required for word cloud formation
    """
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/conversations/wordcloud',
        {'u_bound': u_bound, 'l_bound': l_bound, 'stopword_list': stopword_list, 'month': month}
    )


@router.get("/conversations/input/unique")
async def user_input_unique(
        month: int = Query(default=1, ge=1, le=6),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS),
):
    """
    Returns the list of user inputs that are not included as part of training examples
    """
    queries_not_present = ChatHistoryUtils.unique_user_input(month, current_user.get_bot())
    return Response(data=queries_not_present)


@router.get("/metrics/trend/conversations/time", response_model=Response)
async def conversation_time_trend(month: int = Query(default=6, ge=1, le=6), current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the average conversation time of the bot for previous months
    """
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/trends/conversations/time',
        {'month': month}
    )


@router.get("/metrics/user/fallback/dropoff", response_model=Response)
async def fallback_dropoff(month: int = Query(default=1, ge=1, le=6), current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the list of users that dropped off after encountering fallback
    """
    fallback_action, nlu_fallback_action = DataUtility.load_fallback_actions(current_user.get_bot())
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/fallback/dropoff',
        {'month': month, 'action_fallback': fallback_action, 'nlu_fallback': nlu_fallback_action}
    )


@router.get("/metrics/user/intent/dropoff", response_model=Response)
async def user_intent_dropoff(month: int = Query(default=1, ge=1, le=6), current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the identified intents and their counts for users before dropping off from the conversations.
    """
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/intents/dropoff',
        {'month': month}
    )


@router.get("/metrics/user/sessions/unsuccessful", response_model=Response)
async def unsuccessful_session_count(month: int = Query(default=1, ge=1, le=6), current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the count of sessions that encountered a fallback for a particular user.
    """
    fallback_action, nlu_fallback_action = DataUtility.load_fallback_actions(current_user.get_bot())
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/sessions/unsuccessful',
        {'month': month, 'action_fallback': fallback_action, 'nlu_fallback': nlu_fallback_action}
    )


@router.get("/metrics/user/sessions/total", response_model=Response)
async def total_sessions(month: int = Query(default=1, ge=1, le=6), current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the total session count for users for the past months.
    """
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/sessions/total',
        {'month': month}
    )


@router.delete("/delete/{sender}", response_model=Response)
async def delete_user_chat_history(
        background_tasks: BackgroundTasks, sender: Text, month: int = Query(default=3, ge=1, le=6),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Deletes user chat history up to certain months  min 3 month max 6 months
    """
    HistoryDeletionLogProcessor.is_event_in_progress(bot=current_user.get_bot())
    ChatHistoryUtils.validate_history_endpoint(bot=current_user.get_bot())
    background_tasks.add_task(EventsTrigger.trigger_history_deletion, bot=current_user.get_bot(),
                              user=current_user.get_user(),
                              month=month, sender_id=sender)
    return {"message": "Delete user history initiated. It may take a while. Check logs!"}


@router.delete("/bot/delete", response_model=Response)
async def delete_bot_conversations_history(
        background_tasks: BackgroundTasks, month: int = Query(default=3, ge=1, le=6),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Deletes bot chat history for all users up to certain months  min 1 month max 6 months
    """
    HistoryDeletionLogProcessor.is_event_in_progress(bot=current_user.get_bot())
    ChatHistoryUtils.validate_history_endpoint(bot=current_user.get_bot())
    background_tasks.add_task(EventsTrigger.trigger_history_deletion, bot=current_user.get_bot(), user=current_user.get_user(),
                              month=month)
    return {"message": "Delete chat history initiated. It may take a while. Check logs!"}


@router.get("/delete/logs", response_model=Response)
async def get_delete_history_logs(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)):
    """
    Get history deletion event logs.
    """
    logs = list(HistoryDeletionLogProcessor.get_logs(current_user.get_bot()))
    return Response(data=logs)
