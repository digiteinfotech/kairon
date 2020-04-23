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
    return {"data": {"users": ChatHistory.fetch_chat_users(current_user.get_bot())}}


@router.get("/users/{sender}", response_model=Response)
async def chat_history(
    sender: Text, current_user: User = Depends(auth.get_current_user)
):
    return {
        "data": {
            "history": list(ChatHistory.fetch_chat_history(current_user.get_bot(), sender))
        }
    }

@router.get("/metrics/visitor_hit_fallback", response_model=Response)
async def visitor_hit_fallback(
   current_user: User = Depends(auth.get_current_user)
):
    return {
        "data": ChatHistory.visitor_hit_fallback(current_user.get_bot())
    }


@router.get("/metrics/conversation_steps", response_model=Response)
async def conversation_steps(
   current_user: User = Depends(auth.get_current_user)
):
    return {
        "data": ChatHistory.conversation_steps(current_user.get_bot())
    }


@router.get("/metrics/conversation_time", response_model=Response)
async def conversation_time(
   current_user: User = Depends(auth.get_current_user)
):
    return {
        "data": ChatHistory.conversation_time(current_user.get_bot())
    }
