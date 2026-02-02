from datetime import date

from fastapi import APIRouter, Query
from fastapi import Depends

from kairon.api.models import Response
from kairon.shared.utils import Utility
from ..processor import HistoryProcessor
from ...shared.auth import Authentication

router = APIRouter()


@router.get("/users", response_model=Response)
async def user_with_metrics(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the list of user who has conversation with the agent with steps and time."""
    users, message = HistoryProcessor.user_with_metrics(
        collection, from_date, to_date
    )
    return {"data": {"users": users}, "message": message}


@router.get("/fallback", response_model=Response)
async def visitor_hit_fallback_count(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        fallback_intent: str = Query(default=None),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the number of times the agent hit a fallback (ie. not able to answer) to user queries."""
    visitor_hit_fallback, message = HistoryProcessor.visitor_hit_fallback(
        collection, from_date, to_date, fallback_intent
    )
    return {"data": visitor_hit_fallback, "message": message}


@router.get("/conversation/steps", response_model=Response)
async def conversation_steps(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the number of conversation steps that took place in the chat between the users and the agent."""
    conversation_steps, message = HistoryProcessor.conversation_steps(collection, from_date, to_date)
    return {"data": conversation_steps, "message": message}


@router.get("/users/engaged", response_model=Response)
async def count_engaged_users(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        conversation_step_threshold: int = Query(default=10, ge=2),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the number of engaged users of the bot."""
    engaged_user_count, message = HistoryProcessor.engaged_users(
        collection, from_date, to_date, conversation_step_threshold
    )
    return {"data": engaged_user_count, "message": message}


@router.get("/users/new", response_model=Response)
async def count_new_users(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the number of new users of the bot."""
    user_count, message = HistoryProcessor.new_users(
        collection, from_date, to_date
    )
    return {"data": user_count, "message": message}


@router.get("/conversation/success", response_model=Response)
async def complete_conversations(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        fallback_intent: str = Query(default=None),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the number of successful conversations of the bot, which had no fallback."""
    conversation_count, message = HistoryProcessor.successful_conversations(
        collection, from_date, to_date, fallback_intent
    )
    return {"data": conversation_count, "message": message}


@router.get("/users/retention", response_model=Response)
async def calculate_retention(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the user retention percentage of the bot."""
    retention_count, message = HistoryProcessor.user_retention(
        collection, from_date, to_date
    )
    return {"data": retention_count, "message": message}


@router.get("/intents/topmost", response_model=Response)
async def top_intents(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        top_n: int = Query(default=10, ge=1),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the top n identified intents of the bot."""
    top_intent, message = HistoryProcessor.top_n_intents(
        collection, from_date, to_date, top_n
    )
    return {"data": top_intent, "message": message}


@router.get("/actions/topmost", response_model=Response)
async def top_actions(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        top_n: int = Query(default=10, ge=1),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the top n identified actions of the bot."""
    top_action, message = HistoryProcessor.top_n_actions(
        collection, from_date, to_date, top_n
    )
    return {"data": top_action, "message": message}


@router.get("/users/input", response_model=Response)
async def user_input_count(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the user inputs along with their frequencies."""
    user_inputs, message = HistoryProcessor.user_input_count(
        collection, from_date, to_date
    )
    return {"data": user_inputs, "message": message}


@router.get("/fallback/dropoff", response_model=Response)
async def fallback_dropoff(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        fallback_intent: str = Query(default=None),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the list of users that dropped off after encountering fallback."""
    user_list, message = HistoryProcessor.user_fallback_dropoff(
        collection, from_date, to_date, fallback_intent
    )
    return {"data": user_list, "message": message}


@router.get("/intents/dropoff", response_model=Response)
async def intents_dropoff(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the identified intents and their counts for users before dropping off from the conversations."""
    dropoff_intents, message = HistoryProcessor.intents_before_dropoff(
        collection, from_date, to_date
    )
    return {"data": dropoff_intents, "message": message}


@router.get("/sessions/unsuccessful", response_model=Response)
async def unsuccessful_sessions(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        fallback_intent: str = Query(default=None),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the count of sessions that encountered a fallback for a particular user."""
    user_list, message = HistoryProcessor.unsuccessful_session(
        collection, from_date, to_date, fallback_intent
    )
    return Response(data=user_list, message=message)


@router.get("/sessions/total", response_model=Response)
async def total_sessions(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the total session count for users for the past months."""
    user_list, message = HistoryProcessor.session_count(
        collection, from_date, to_date
    )
    return Response(data=user_list, message=message)
