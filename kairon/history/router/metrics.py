from fastapi import APIRouter
from kairon.api.models import Response
from fastapi import Depends

from ..models import HistoryQuery
from ..processor import ChatHistory
from ..utils import Authentication

router = APIRouter()


@router.get("/users", response_model=Response)
async def user_with_metrics(
        request: HistoryQuery = HistoryQuery(),
        collection: str = Depends(Authentication.authenticate_and_get_collection)):
    """
    Fetches the list of user who has conversation with the agent with steps anf time
    """
    users, message = ChatHistory.user_with_metrics(
        collection, request.month
    )
    return {"data": {"users": users}, "message": message}


@router.get("/fallback", response_model=Response)
async def visitor_hit_fallback_count(request: HistoryQuery = HistoryQuery(),
                                     collection: str = Depends(Authentication.authenticate_and_get_collection)):
    """
    Fetches the number of times the agent hit a fallback (ie. not able to answer) to user queries
    """
    visitor_hit_fallback, message = ChatHistory.visitor_hit_fallback(
        collection, request.month, request.action_fallback, request.nlu_fallback
    )
    return {"data": visitor_hit_fallback, "message": message}


@router.get("/conversation/steps", response_model=Response)
async def conversation_steps(request: HistoryQuery = HistoryQuery(),
                             collection: str = Depends(Authentication.authenticate_and_get_collection)):
    """
     Fetches the number of conversation steps that took place in the chat between the users and the agent
     """
    conversation_steps, message = ChatHistory.conversation_steps(collection, request.month)
    return {"data": conversation_steps, "message": message}


@router.get("/conversation/time", response_model=Response)
async def conversation_time(request: HistoryQuery = HistoryQuery(),
                            collection: str = Depends(Authentication.authenticate_and_get_collection)):
    """
    Fetches the duration of the chat that took place between the users and the agent"""
    conversation_time, message = ChatHistory.conversation_time(collection, request.month)
    return {"data": conversation_time, "message": message}


@router.get("/users/engaged", response_model=Response)
async def count_engaged_users(request: HistoryQuery = HistoryQuery(),
                              collection: str = Depends(Authentication.authenticate_and_get_collection)):
    """
    Fetches the number of engaged users of the bot
    """
    engaged_user_count, message = ChatHistory.engaged_users(
        collection, request.month, request.conversation_step_threshold
    )
    return {"data": engaged_user_count, "message": message}


@router.get("/users/new", response_model=Response)
async def count_new_users(request: HistoryQuery = HistoryQuery(),
                          collection: str = Depends(Authentication.authenticate_and_get_collection)):
    """
    Fetches the number of new users of the bot
    """
    user_count, message = ChatHistory.new_users(
        collection, request.month
    )
    return {"data": user_count, "message": message}


@router.get("/conversation/success", response_model=Response)
async def complete_conversations(request: HistoryQuery = HistoryQuery(),
                                 collection: str = Depends(Authentication.authenticate_and_get_collection)):
    """
    Fetches the number of successful conversations of the bot, which had no fallback
    """
    conversation_count, message = ChatHistory.successful_conversations(
        collection, request.month, request.action_fallback, request.nlu_fallback
    )
    return {"data": conversation_count, "message": message}


@router.get("/users/retention", response_model=Response)
async def calculate_retention(request: HistoryQuery = HistoryQuery(),
                              collection: str = Depends(Authentication.authenticate_and_get_collection)):
    """
    Fetches the user retention percentage of the bot
    """
    retention_count, message = ChatHistory.user_retention(
        collection, request.month
    )
    return {"data": retention_count, "message": message}
