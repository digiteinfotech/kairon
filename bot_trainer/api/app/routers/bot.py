from fastapi import APIRouter
from fastapi import Depends, Path

from bot_trainer.api.auth import Authentication
from bot_trainer.api.models import *
from bot_trainer.data_processor.processor import MongoProcessor
from bot_trainer.data_processor.data_objects import *

router = APIRouter()
auth = Authentication()
mongo_processor = MongoProcessor()


@router.get("/intents", response_model=Response)
async def get_intents(current_user: User = Depends(auth.get_current_user)):
    return {"data": mongo_processor.get_intents(current_user.bot)}


@router.post("/intents", response_model=Response)
async def add_intents(
    request_data: RequestData, current_user: User = Depends(auth.get_current_user)
):
    id = mongo_processor.add_intent(
        text=request_data.data, bot=current_user.bot, user=current_user.email
    )
    return {"message": "Intent added successfully!", "data": {"_id": id}}


@router.get("/training_examples/{intent}", response_model=Response)
async def get_training_examples(
    intent: str, current_user: User = Depends(auth.get_current_user)
):
    return {
        "data": list(mongo_processor.get_training_examples(intent, current_user.bot))
    }


@router.post("/training_examples/{intent}", response_model=Response)
async def add_training_examples(
    intent: str,
    request_data: RequestData,
    current_user: User = Depends(auth.get_current_user),
):
    id = mongo_processor.add_training_example(
        request_data.data, intent, current_user.bot, current_user.email
    )
    return {"message": "Training Example added successfully!", "data": {"_id": id}}


@router.delete("/training_examples", response_model=Response)
async def remove_training_examples(
    request_data: RequestData, current_user: User = Depends(auth.get_current_user)
):
    mongo_processor.remove_document(
        TrainingExamples, request_data.data, current_user.bot, current_user.email
    )
    return {"message": "Training Example removed successfully!"}


@router.get("/responses/{utterance}", response_model=Response)
async def get_responses(
    utterance: str, current_user: User = Depends(auth.get_current_user)
):
    return {"data": list(mongo_processor.get_response(utterance, current_user.bot))}


@router.post("/responses/{utterance}", response_model=Response)
async def add_responses(
    request_data: RequestData,
    utterance: str,
    current_user: User = Depends(auth.get_current_user),
):
    id = mongo_processor.add_text_response(
        request_data.data, utterance, current_user.bot, current_user.email
    )
    return {"message": "Response added successfully!", "data": {"_id": id}}


@router.delete("/responses", response_model=Response)
async def remove_responses(
    request_data: RequestData, current_user: User = Depends(auth.get_current_user)
):
    mongo_processor.remove_document(
        Responses, request_data.data, current_user.bot, current_user.email
    )
    return {
        "message": "Response removed successfully!",
    }
