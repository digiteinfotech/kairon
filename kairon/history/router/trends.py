from datetime import datetime, date, timedelta

from fastapi import APIRouter, Query
from kairon.api.models import Response
from fastapi import Depends

from ..processor import HistoryProcessor
from ...shared.auth import Authentication

router = APIRouter()


@router.get("/users/engaged", response_model=Response)
async def engaged_users(
        from_date: date = Query(default=(datetime.utcnow() - timedelta(180)).date()),
        to_date: date = Query(default=datetime.utcnow().date()),
        conversation_step_threshold: int = Query(default=10, ge=2),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the counts of engaged users of the bot for previous months."""
    range_value, message = HistoryProcessor.engaged_users_range(
        collection, from_date, to_date, conversation_step_threshold
    )
    return {"data": range_value, "message": message}


@router.get("/users/new", response_model=Response)
async def new_users(
        from_date: date = Query(default=(datetime.utcnow() - timedelta(180)).date()),
        to_date: date = Query(default=datetime.utcnow().date()),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the counts of new users of the bot for previous months."""
    range_value, message = HistoryProcessor.new_users_range(
        collection, from_date, to_date
    )
    return {"data": range_value, "message": message}


@router.get("/conversations/success", response_model=Response)
async def complete_conversation(
        from_date: date = Query(default=(datetime.utcnow() - timedelta(180)).date()),
        to_date: date = Query(default=datetime.utcnow().date()),
        action_fallback: str = Query(default="action_default_fallback"),
        nlu_fallback: str = Query(default=None),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the counts of successful conversations of the bot for previous months."""
    range_value, message = HistoryProcessor.successful_conversation_range(
        collection, from_date, to_date, action_fallback, nlu_fallback
    )
    return {"data": range_value, "message": message}


@router.get("/users/retention", response_model=Response)
async def user_retention(
        from_date: date = Query(default=(datetime.utcnow() - timedelta(180)).date()),
        to_date: date = Query(default=datetime.utcnow().date()),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the counts of user retention percentages of the bot for previous months."""
    range_value, message = HistoryProcessor.user_retention_range(
        collection, from_date, to_date
    )
    return {"data": range_value, "message": message}


@router.get("/fallback", response_model=Response)
async def fallback(
        from_date: date = Query(default=(datetime.utcnow() - timedelta(180)).date()),
        to_date: date = Query(default=datetime.utcnow().date()),
        action_fallback: str = Query(default="action_default_fallback"),
        nlu_fallback: str = Query(default=None),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the fallback count of the bot for previous months."""
    range_value, message = HistoryProcessor.fallback_count_range(
        collection, from_date, to_date, action_fallback, nlu_fallback
    )
    return {"data": range_value, "message": message}


@router.get("/conversations/total", response_model=Response)
async def total_conversations(
        from_date: date = Query(default=(datetime.utcnow() - timedelta(180)).date()),
        to_date: date = Query(default=datetime.utcnow().date()),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the counts of conversations of the bot for previous months."""
    range_value, message = HistoryProcessor.total_conversation_range(
        collection, from_date, to_date
    )
    return {"data": range_value, "message": message}


@router.get("/conversations/steps", response_model=Response)
async def conversation_steps(
        from_date: date = Query(default=(datetime.utcnow() - timedelta(180)).date()),
        to_date: date = Query(default=datetime.utcnow().date()),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the average conversation steps of the bot for previous months."""
    range_value, message = HistoryProcessor.average_conversation_step_range(
        collection, from_date, to_date
    )
    return {"data": range_value, "message": message}
