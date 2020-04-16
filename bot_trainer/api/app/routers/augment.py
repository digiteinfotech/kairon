from fastapi import APIRouter
from fastapi import Depends

from bot_trainer.api.auth import Authentication
from bot_trainer.api.models import *
from bot_trainer.data_processor.processor import MongoProcessor

router = APIRouter()
auth = Authentication()
mongo_processor = MongoProcessor()


@router.post("/questions", response_model=Response)
async def questions(current_user: User = Depends(auth.get_current_user)):
    return {"data": {"questions": []}}
