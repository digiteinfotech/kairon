from datetime import date
from io import BytesIO
from typing import Text

from fastapi import APIRouter, Security, Depends
from fastapi import Query
from starlette.responses import StreamingResponse

from kairon.api.app.routers.bot.action import mongo_processor
from kairon.api.models import Response
from kairon.events.definitions.history_delete import DeleteHistoryEvent
from kairon.shared.auth import Authentication
from kairon.shared.constants import TESTER_ACCESS, ADMIN_ACCESS
from kairon.shared.data.data_objects import ConversationsHistoryDeleteLogs
from kairon.shared.data.history_log_processor import HistoryDeletionLogProcessor
from kairon.shared.data.utils import DataUtility, ChatHistoryUtils
from kairon.shared.models import User
from kairon.shared.utils import Utility

router = APIRouter()


@router.get("/users", response_model=Response)
async def chat_history_users(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the list of user who has conversation with the agent
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/conversations/users?from_date={from_date}&to_date={to_date}'
    )


@router.get("/users/{sender:path}", response_model=Response)
async def chat_history(
        sender: Text,
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the list of conversation with the agent by particular user
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/conversations/users/{sender}?from_date={from_date}&to_date={to_date}'
    )


@router.get("/metrics/users", response_model=Response)
async def user_with_metrics(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the list of user who has conversation with the agent with steps anf time
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/users?from_date={from_date}&to_date={to_date}'
    )


@router.get("/metrics/fallback", response_model=Response)
async def visitor_hit_fallback(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the number of times the agent hit a fallback (ie. not able to answer) to user queries
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    fallback_intent = DataUtility.get_fallback_intent(current_user.get_bot(), current_user.get_user())
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/fallback?from_date={from_date}&to_date={to_date}'
        f'&fallback_intent={fallback_intent}'
    )


@router.get("/metrics/conversation/steps", response_model=Response)
async def conversation_steps(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
     Fetches the number of conversation steps that took place in the chat between the users and the agent
     """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/conversation/steps?from_date={from_date}&to_date={to_date}'
    )


@router.get("/metrics/conversation/time", response_model=Response)
async def conversation_time(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the duration of the chat that took place between the users and the agent
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/conversation/time?from_date={from_date}&to_date={to_date}'
    )


@router.get("/metrics/user/engaged", response_model=Response)
async def count_engaged_users(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        conversation_step_threshold: int = Query(default=10, ge=2),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):

    """
    Fetches the number of engaged users of the bot
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/users/engaged'
        f'?from_date={from_date}&to_date={to_date}&conversation_step_threshold={conversation_step_threshold}'
    )


@router.get("/metrics/user/new", response_model=Response)
async def count_new_users(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the number of new users of the bot
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/users/new?from_date={from_date}&to_date={to_date}'
    )


@router.get("/metrics/conversation/success", response_model=Response)
async def complete_conversations(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the number of successful conversations of the bot, which had no fallback
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    fallback_intent = DataUtility.get_fallback_intent(current_user.get_bot(), current_user.get_user())
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/conversation/success?from_date={from_date}'
        f'&to_date={to_date}&fallback_intent={fallback_intent}'
    )


@router.get("/metrics/user/retention", response_model=Response)
async def calculate_retention(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the user retention percentage of the bot
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/users/retention?from_date={from_date}&to_date={to_date}'
    )


@router.get("/metrics/trend/user/engaged", response_model=Response)
async def engaged_users_trend(
        from_date: date = Depends(Utility.get_back_date_6month),
        to_date: date = Depends(Utility.get_to_date),
        conversation_step_threshold: int = Query(default=10, ge=2),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):

    """
    Fetches the counts of engaged users of the bot for previous months
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/trends/users/engaged?from_date={from_date}&to_date={to_date}'
        f'&conversation_step_threshold={conversation_step_threshold}'
    )


@router.get("/metrics/trend/user/new", response_model=Response)
async def new_users_trend(
        from_date: date = Depends(Utility.get_back_date_6month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the counts of new users of the bot for previous months
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/trends/users/new?from_date={from_date}&to_date={to_date}'
    )


@router.get("/metrics/trend/conversation/success", response_model=Response)
async def complete_conversation_trend(
        from_date: date = Depends(Utility.get_back_date_6month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the counts of successful conversations of the bot for previous months
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    fallback_intent = DataUtility.get_fallback_intent(current_user.get_bot(), current_user.get_user())
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/trends/conversations/success?from_date={from_date}'
        f'&to_date={to_date}&fallback_intent={fallback_intent}'
    )


@router.get("/metrics/trend/user/retention", response_model=Response)
async def retention_trend(
        from_date: date = Depends(Utility.get_back_date_6month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the counts of user retention percentages of the bot for previous months
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/trends/users/retention?from_date={from_date}&to_date={to_date}'
    )


@router.get("/metrics/trend/user/fallback", response_model=Response)
async def fallback_trend(
        from_date: date = Depends(Utility.get_back_date_6month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the fallback count of the bot for previous months
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    fallback_intent = DataUtility.get_fallback_intent(current_user.get_bot(), current_user.get_user())
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/trends/fallback?from_date={from_date}&to_date={to_date}'
        f'&fallback_intent={fallback_intent}'
    )


@router.get("/conversations", response_model=Response)
async def flat_conversations(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the flattened conversation data of the bot for previous months
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/conversations/?from_date={from_date}&to_date={to_date}'
    )

@router.get("/conversations/agentic_flow", response_model=Response)
async def fetch_agentic_flow_conversations(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the flattened conversation data of the bot for previous months
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/conversations/agentic_flow?from_date={from_date}&to_date={to_date}'
    )

@router.get("/conversations/agentic_flow/user/{sender:path}", response_model=Response)
async def fetch_agentic_flow_user_conversations(
        sender: Text,
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the list of conversation with the agent by particular user
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/conversations/agentic_flow/user/{sender}?from_date={from_date}&to_date={to_date}'
    )




@router.get("/conversations/download")
async def download_conversations(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS),
):
    """
    Downloads conversation history of the bot, for the specified months
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    response = Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/conversations/download?from_date={from_date}&to_date={to_date}',
        return_json=False
    )
    return StreamingResponse(BytesIO(response.content), media_type='text/csv', headers={'Content-Disposition': f"attachment; filename=conversation_history_{current_user.get_bot()}{date.today().strftime('_%d_%m_%y.csv')}"})


@router.get("/metrics/intents/topmost", response_model=Response)
async def top_n_intents(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        top_n: int = Query(default=10, ge=1),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the top n identified intents of the bot
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/intents/topmost?from_date={from_date}'
        f'&to_date={to_date}&top_n={top_n}'
    )


@router.get("/metrics/actions/topmost", response_model=Response)
async def top_n_actions(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        top_n: int = Query(default=10, ge=1),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the top n identified actions of the bot
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/actions/topmost?from_date={from_date}&to_date={to_date}'
        f'&top_n={top_n}'
    )


@router.get("/metrics/trend/conversations/total", response_model=Response)
async def total_conversation_trend(
        from_date: date = Depends(Utility.get_back_date_6month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the counts of conversations of the bot for previous months
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/trends/conversations/total?from_date={from_date}&to_date={to_date}'
    )


@router.get("/metrics/trend/conversations/steps", response_model=Response)
async def conversation_step_trend(
        from_date: date = Depends(Utility.get_back_date_6month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the average conversation steps of the bot for previous months
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/trends/conversations/steps?from_date={from_date}&to_date={to_date}'
    )


@router.get("/conversations/wordcloud")
async def word_cloud(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        l_bound: float = Query(default=0, ge=0, lt=1),
        u_bound: float = Query(default=1, gt=0, le=1),
        stopword_list: list = Query(default=None),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS),
):
    """
    Returns the conversation string that is required for word cloud formation
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/conversations/wordcloud?from_date={from_date}&to_date={to_date}'
        f'&u_bound={u_bound}&l_bound={l_bound}&stopword_list={stopword_list}'
    )


@router.get("/conversations/input/unique")
async def user_input_unique(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS),
):
    """
    Returns the list of user inputs that are not included as part of training examples
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    queries_not_present = ChatHistoryUtils.unique_user_input(from_date, to_date, current_user.get_bot())
    return Response(data=queries_not_present)


@router.get("/metrics/trend/conversations/time", response_model=Response)
async def conversation_time_trend(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the average conversation time of the bot for previous months
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/trends/conversations/time?from_date={from_date}&to_date={to_date}'
    )


@router.get("/metrics/user/fallback/dropoff", response_model=Response)
async def fallback_dropoff(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the list of users that dropped off after encountering fallback
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    fallback_intent = DataUtility.get_fallback_intent(current_user.get_bot(), current_user.get_user())
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/fallback/dropoff?from_date={from_date}'
        f'&to_date={to_date}&fallback_intent={fallback_intent}'
    )


@router.get("/metrics/user/intent/dropoff", response_model=Response)
async def user_intent_dropoff(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the identified intents and their counts for users before dropping off from the conversations.
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/intents/dropoff?from_date={from_date}&to_date={to_date}'
    )


@router.get("/metrics/user/sessions/unsuccessful", response_model=Response)
async def unsuccessful_session_count(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the count of sessions that encountered a fallback for a particular user.
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    fallback_intent = DataUtility.get_fallback_intent(current_user.get_bot(), current_user.get_user())
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
            f'/api/history/{current_user.get_bot()}/metrics/sessions/unsuccessful?from_date={from_date}'
        f'&to_date={to_date}&fallback_intent={fallback_intent}'
    )


@router.get("/metrics/user/sessions/total", response_model=Response)
async def total_sessions(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches the total session count for users for the past months.
    """
    Utility.validate_from_date_and_to_date(from_date, to_date)
    return Utility.trigger_history_server_request(
        current_user.get_bot(),
        f'/api/history/{current_user.get_bot()}/metrics/sessions/total?from_date={from_date}&to_date={to_date}'
    )


@router.delete("/delete/{sender}", response_model=Response)
async def delete_user_chat_history(
        sender: Text,
        till_date: date = Depends(Utility.get_till_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Deletes user chat history up to certain months  min 3 month max 6 months
    """
    event = DeleteHistoryEvent(
        current_user.get_bot(), current_user.get_user(), till_date=till_date, sender_id=sender
    )
    event.validate()
    event.enqueue()
    return {"message": "Delete user history initiated. It may take a while. Check logs!"}


@router.delete("/bot/delete", response_model=Response)
async def delete_bot_conversations_history(
        till_date: date = Depends(Utility.get_till_date),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Deletes bot chat history for all users up to certain months  min 1 month max 6 months
    """
    event = DeleteHistoryEvent(current_user.get_bot(), current_user.get_user(), till_date=till_date)
    event.validate()
    event.enqueue()
    return {"message": "Delete chat history initiated. It may take a while. Check logs!"}


@router.get("/delete/logs", response_model=Response)
async def get_delete_history_logs(
        start_idx: int = 0, page_size: int = 10,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Get history deletion event logs.
    """
    logs = list(HistoryDeletionLogProcessor.get_logs(current_user.get_bot(), start_idx, page_size))
    row_cnt = mongo_processor.get_row_count(ConversationsHistoryDeleteLogs, current_user.get_bot())
    data = {
        "logs": logs,
        "total": row_cnt
    }
    return Response(data=data)
