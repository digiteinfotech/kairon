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
    """ This function returns the list of the chatbot users """
    return {"data": {"users": ChatHistory.fetch_chat_users(current_user.get_bot())}}


@router.get("/users/{sender}", response_model=Response)
async def chat_history(
    sender: Text, current_user: User = Depends(auth.get_current_user)
):
    """ This function returns the chat history for a particular user of the chatbot """
    return {
        "data": {
            "history": list(
                ChatHistory.fetch_chat_history(current_user.get_bot(), sender)
            )
        }
    }


@router.get("/metrics/visitor_hit_fallback", response_model=Response)
async def visitor_hit_fallback(current_user: User = Depends(auth.get_current_user)):
    """ This function returns the number of times the bot hit
        a fallback (the bot admitting to not having a reply for a given
        text/query) for a given user """
    return {"data": ChatHistory.visitor_hit_fallback(current_user.get_bot())}


@router.get("/metrics/conversation_steps", response_model=Response)
async def conversation_steps(current_user: User = Depends(auth.get_current_user)):
    """ This function returns the number of conversation steps that took place in the chat
        between the user and the chatbot """
    return {"data": ChatHistory.conversation_steps(current_user.get_bot())}


@router.get("/metrics/conversation_time", response_model=Response)
async def conversation_time(current_user: User = Depends(auth.get_current_user)):
    """ This returns the duration of the chat that took place between the user and the
        chatbot """
    return {"data": ChatHistory.conversation_time(current_user.get_bot())}
