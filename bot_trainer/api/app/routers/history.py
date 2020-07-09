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
    """
    Fetches the list of user who has conversation with the agent
    """
    users, message = ChatHistory.fetch_chat_users(current_user.get_bot())
    return {"data": {"users": users}, "message": message}


@router.get("/users/{sender}", response_model=Response)
async def chat_history(
    sender: Text, current_user: User = Depends(auth.get_current_user)
):
    """
    Fetches the list of conversation with the agent by particular user
    """
    history, message = ChatHistory.fetch_chat_history(current_user.get_bot(), sender)
    return {
        "data": {
            "history": list(
                history
            )
        },
        "message": message
    }


@router.get("/metrics/visitor_hit_fallback", response_model=Response)
async def visitor_hit_fallback(current_user: User = Depends(auth.get_current_user)):
    """
    Fetches the number of times the agent hit a fallback (ie. not able to answer) to user queries
    """
    visitor_hit_fallback, message = ChatHistory.visitor_hit_fallback(current_user.get_bot())
    return {"data": visitor_hit_fallback, "message": message}


@router.get("/metrics/conversation_steps", response_model=Response)
async def conversation_steps(current_user: User = Depends(auth.get_current_user)):
    """
     Fetches the number of conversation steps that took place in the chat between the users and the agent
     """
    conversation_steps, message = ChatHistory.conversation_steps(current_user.get_bot())
    return {"data": conversation_steps, "message": message}


@router.get("/metrics/conversation_time", response_model=Response)
async def conversation_time(current_user: User = Depends(auth.get_current_user)):
    """
    Fetches the duration of the chat that took place between the users and the agent"""
    conversation_time, message = ChatHistory.conversation_time(current_user.get_bot())
    return {"data": conversation_time, "message": message}
