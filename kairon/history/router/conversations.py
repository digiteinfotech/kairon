import os
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import FileResponse
from kairon.api.models import Response
from fastapi import Depends
from typing import Text

from kairon.shared.utils import Utility
from ..models import HistoryQuery
from ..processor import HistoryProcessor
from ...shared.auth import Authentication

router = APIRouter()


@router.get("/", response_model=Response)
async def flat_conversations(request: HistoryQuery = HistoryQuery(),
                             collection: str = Depends(Authentication.authenticate_and_get_collection)):
    """Fetches the flattened conversation data of the bot for previous months."""
    flat_data, message = HistoryProcessor.flatten_conversations(
        collection, request.month, request.sort_by_date
    )
    return {"data": flat_data, "message": message}


@router.get("/download")
async def download_conversations(
        background_tasks: BackgroundTasks,
        request: HistoryQuery = HistoryQuery(),
        collection: str = Depends(Authentication.authenticate_and_get_collection),
):
    """Downloads conversation history of the bot, for the specified months."""
    conversation_data, message = HistoryProcessor.flatten_conversations(collection, request.month, request.sort_by_date)
    file, temp_path = Utility.download_csv(conversation_data, message)
    response = FileResponse(
        file, filename=os.path.basename(file), background=background_tasks
    )
    response.headers[
        "Content-Disposition"
    ] = "attachment; filename=" + os.path.basename(file)
    background_tasks.add_task(Utility.delete_directory, temp_path)
    return response


@router.get("/users", response_model=Response)
async def chat_history_users(request: HistoryQuery = HistoryQuery(),
                             collection: str = Depends(Authentication.authenticate_and_get_collection)):
    """Fetches the list of user who has conversation with the agent."""
    users, message = HistoryProcessor.fetch_chat_users(collection, request.month)
    return {"data": {"users": users}, "message": message}


@router.get("/users/{sender}", response_model=Response)
async def chat_history(sender: Text,
                       request: HistoryQuery = HistoryQuery(),
                       collection: str = Depends(Authentication.authenticate_and_get_collection)):
    """Fetches the list of conversation with the agent by particular user."""
    history, message = HistoryProcessor.fetch_chat_history(collection, sender, request.month)
    return {"data": {"history": list(history)}, "message": message}


@router.get("/wordcloud", response_model=Response)
async def word_cloud(request: HistoryQuery = HistoryQuery(),
                             collection: str = Depends(Authentication.authenticate_and_get_collection)):
    """Fetches the string required for word cloud formation"""
    sentence, message = HistoryProcessor.word_cloud(collection, request.u_bound, request.l_bound,
                                                    request.stopwords, request.month)
    return {"data": {"conversation_string": sentence}, "message": message}

