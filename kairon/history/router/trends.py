from fastapi import APIRouter
from kairon.api.auth import Authentication
from kairon.api.models import Response, User
from fastapi import Depends

from ..models import HistoryQuery
from ..processor import ChatHistory

router = APIRouter()


@router.get("/users/engaged", response_model=Response)
async def engaged_users(request: HistoryQuery = HistoryQuery(month=6),
                        current_user: User = Depends(Authentication.authenticate_user)):
    """
    Fetches the counts of engaged users of the bot for previous months
    """
    range_value, message = ChatHistory.engaged_users_range(
        current_user.get_bot(), request.month, request.conversation_step_threshold
    )
    return {"data": range_value, "message": message}


@router.get("/users/new", response_model=Response)
async def new_users(request: HistoryQuery = HistoryQuery(month=6),
                    current_user: User = Depends(Authentication.authenticate_user)):
    """
    Fetches the counts of new users of the bot for previous months
    """
    range_value, message = ChatHistory.new_users_range(
        current_user.get_bot(), request.month
    )
    return {"data": range_value, "message": message}


@router.get("/conversations/success", response_model=Response)
async def complete_conversation(request: HistoryQuery = HistoryQuery(month=6),
                                current_user: User = Depends(Authentication.authenticate_user)):
    """
    Fetches the counts of successful conversations of the bot for previous months
    """
    range_value, message = ChatHistory.successful_conversation_range(
        current_user.get_bot(), request.month
    )
    return {"data": range_value, "message": message}


@router.get("/users/retention", response_model=Response)
async def user_retention(request: HistoryQuery = HistoryQuery(month=6),
                         current_user: User = Depends(Authentication.authenticate_user)):
    """
    Fetches the counts of user retention percentages of the bot for previous months
    """
    range_value, message = ChatHistory.user_retention_range(
        current_user.get_bot(), request.month
    )
    return {"data": range_value, "message": message}


@router.get("/fallback", response_model=Response)
async def fallback(request: HistoryQuery = HistoryQuery(month=6),
                   current_user: User = Depends(Authentication.authenticate_user)):
    """
    Fetches the fallback count of the bot for previous months
    """
    range_value, message = ChatHistory.fallback_count_range(
        current_user.get_bot(), request.month
    )
    return {"data": range_value, "message": message}
