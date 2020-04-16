from fastapi import APIRouter

from bot_trainer.api.auth import Authentication
from bot_trainer.data_processor.history import ChatHistory
from bot_trainer.api.models import Response, User
from fastapi import Depends
from typing import Text

router = APIRouter()
auth = Authentication()

@router.get("/users", response_model=Response)
async def chat_history_users(current_user: User = Depends(auth.get_current_user)):
    return {"data":{"users":ChatHistory.fetch_chat_users(current_user.bot)}}


@router.post("/history/users/{sender}", response_model=Response)
async def chat_history(sender: Text, current_user: User = Depends(auth.get_current_user)):
    return {"data": {"history": list(ChatHistory.fetch_chat_history(current_user.bot, sender))}}