import os
from datetime import datetime, date, timedelta

from fastapi import APIRouter, BackgroundTasks, Query
from fastapi.responses import FileResponse
from kairon.api.models import Response
from fastapi import Depends
from typing import Text

from kairon.shared.utils import Utility
from ..processor import HistoryProcessor
from ...shared.auth import Authentication

router = APIRouter()


@router.get("/", response_model=Response)
async def flat_conversations(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the flattened conversation data of the bot for previous months."""
    flat_data, message = HistoryProcessor.flatten_conversations(
        f"{collection}_flattened", from_date, to_date
    )
    return {"data": flat_data, "message": message}


@router.get("/agentic_flow", response_model=Response)
async def agentic_flow_conversations(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the flattened conversation data of the bot for previous months."""
    flat_data, message = HistoryProcessor.flatten_conversations(
        f"{collection}_agent", from_date, to_date
    )
    return {"data": flat_data, "message": message}


@router.get("/agentic_flow/user/{sender:path}", response_model=Response)
async def agentic_flow_user_history(
        sender: Text,
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the list of conversation with the agent by particular user."""
    history, message = HistoryProcessor.fetch_chat_history(f"{collection}_agent", sender, from_date, to_date)
    return {"data": {"history": list(history)}, "message": message}


@router.get("/download")
async def download_conversations(
        background_tasks: BackgroundTasks,
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        collection: str = Depends(Authentication.authenticate_and_get_collection),
):
    """Downloads conversation history of the bot, for the specified months."""
    conversation_data, _ = HistoryProcessor.flatten_conversations(f"{collection}_flattened", from_date, to_date)
    file, temp_path = Utility.download_csv(conversation_data.get("conversation_data"))
    response = FileResponse(
        file, filename=os.path.basename(file), background=background_tasks
    )
    response.headers[
        "Content-Disposition"
    ] = "attachment; filename=" + os.path.basename(file)
    background_tasks.add_task(Utility.delete_directory, temp_path)
    return response


@router.get("/users", response_model=Response)
async def chat_history_users(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the list of user who has conversation with the agent."""
    users, message = HistoryProcessor.fetch_chat_users(collection, from_date, to_date)
    return {"data": {"users": users}, "message": message}


@router.get("/users/{sender:path}", response_model=Response)
async def chat_history(
        sender: Text,
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the list of conversation with the agent by particular user."""
    history, message = HistoryProcessor.fetch_chat_history(f"{collection}_flattened", sender, from_date, to_date)
    return {"data": {"history": list(history)}, "message": message}


@router.get("/wordcloud", response_model=Response)
async def word_cloud(
        from_date: date = Depends(Utility.get_back_date_1month),
        to_date: date = Depends(Utility.get_to_date),
        l_bound: float = Query(default=0, ge=0, lt=1),
        u_bound: float = Query(default=1, gt=0, le=1),
        stopword_list: list = Query(default=None),
        collection: str = Depends(Authentication.authenticate_and_get_collection)
):
    """Fetches the string required for word cloud formation."""
    sentence, message = HistoryProcessor.word_cloud(collection, u_bound, l_bound, stopword_list, from_date, to_date)
    return {"data": sentence, "message": message}
