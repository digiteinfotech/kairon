from fastapi import APIRouter
from kairon.api.models import Response
from fastapi import Depends

from ..models import HistoryQuery
from ..processor import HistoryProcessor
from ...shared.auth import Authentication

router = APIRouter()


@router.get("/users/engaged", response_model=Response)
async def engaged_users(request: HistoryQuery = HistoryQuery(month=6),
                        collection: str = Depends(Authentication.authenticate_and_get_collection)):
    """Fetches the counts of engaged users of the bot for previous months."""
    range_value, message = HistoryProcessor.engaged_users_range(
        collection, request.month, request.conversation_step_threshold
    )
    return {"data": range_value, "message": message}


@router.get("/users/new", response_model=Response)
async def new_users(request: HistoryQuery = HistoryQuery(month=6),
                    collection: str = Depends(Authentication.authenticate_and_get_collection)):
    """Fetches the counts of new users of the bot for previous months."""
    range_value, message = HistoryProcessor.new_users_range(
        collection, request.month
    )
    return {"data": range_value, "message": message}


@router.get("/conversations/success", response_model=Response)
async def complete_conversation(request: HistoryQuery = HistoryQuery(month=6),
                                collection: str = Depends(Authentication.authenticate_and_get_collection)):
    """Fetches the counts of successful conversations of the bot for previous months."""
    range_value, message = HistoryProcessor.successful_conversation_range(
        collection, request.month, request.action_fallback, request.nlu_fallback
    )
    return {"data": range_value, "message": message}


@router.get("/users/retention", response_model=Response)
async def user_retention(request: HistoryQuery = HistoryQuery(month=6),
                         collection: str = Depends(Authentication.authenticate_and_get_collection)):
    """Fetches the counts of user retention percentages of the bot for previous months."""
    range_value, message = HistoryProcessor.user_retention_range(
        collection, request.month
    )
    return {"data": range_value, "message": message}


@router.get("/fallback", response_model=Response)
async def fallback(request: HistoryQuery = HistoryQuery(month=6),
                   collection: str = Depends(Authentication.authenticate_and_get_collection)):
    """Fetches the fallback count of the bot for previous months."""
    range_value, message = HistoryProcessor.fallback_count_range(
        collection, request.month, request.action_fallback, request.nlu_fallback
    )
    return {"data": range_value, "message": message}


@router.get("/conversations/total", response_model=Response)
async def total_conversations(request: HistoryQuery = HistoryQuery(month=6),
                                collection: str = Depends(Authentication.authenticate_and_get_collection)):
    """Fetches the counts of conversations of the bot for previous months."""
    range_value, message = HistoryProcessor.total_conversation_range(
        collection, request.month
    )
    return {"data": range_value, "message": message}


@router.get("/conversations/steps", response_model=Response)
async def conversation_steps(request: HistoryQuery = HistoryQuery(month=6),
                                collection: str = Depends(Authentication.authenticate_and_get_collection)):
    """Fetches the average conversation steps of the bot for previous months."""
    range_value, message = HistoryProcessor.average_conversation_step_range(
        collection, request.month
    )
    return {"data": range_value, "message": message}


