from fastapi import APIRouter
from fastapi import Depends

from bot_trainer.api.auth import Authentication
from bot_trainer.api.models import *
from bot_trainer.data_processor.data_objects import *
from bot_trainer.data_processor.processor import MongoProcessor, AgentProcessor
from bot_trainer.train import train_model_from_mongo
import requests
router = APIRouter()
auth = Authentication()
mongo_processor = MongoProcessor()


@router.get("/intents", response_model=Response)
async def get_intents(current_user: User = Depends(auth.get_current_user)):
    return Response(data=mongo_processor.get_intents(current_user.get_bot())).dict()


@router.post("/intents", response_model=Response)
async def add_intents(
    request_data: TextData, current_user: User = Depends(auth.get_current_user)
):
    id = mongo_processor.add_intent(
        text=request_data.data, bot=current_user.get_bot(), user=current_user.get_user()
    )
    return {"message": "Intent added successfully!", "data": {"_id": id}}

@router.post("/intents/predict", response_model=Response)
async def predict_intent(
    request_data: TextData, current_user: User = Depends(auth.get_current_user)
):
    model = AgentProcessor.get_agent(current_user.get_bot())
    response = await model.parse_message_using_nlu_interpreter(request_data.data)
    intent = response.get("intent").get("name") if response else None
    confidence = response.get("intent").get("confidence") if response else None
    return {"data": {"intent": intent, "confidence": confidence}}


@router.get("/training_examples/{intent}", response_model=Response)
async def get_training_examples(
    intent: str, current_user: User = Depends(auth.get_current_user)
):
    return {
        "data": list(
            mongo_processor.get_training_examples(intent, current_user.get_bot())
        )
    }


@router.post("/training_examples/{intent}", response_model=Response)
async def add_training_examples(
    intent: str,
    request_data: ListData,
    current_user: User = Depends(auth.get_current_user),
):
    results = list(mongo_processor.add_training_example(
        request_data.data, intent, current_user.get_bot(), current_user.get_user()
    ))
    return {"data": results}


@router.delete("/training_examples", response_model=Response)
async def remove_training_examples(
    request_data: TextData, current_user: User = Depends(auth.get_current_user)
):
    mongo_processor.remove_document(
        TrainingExamples, request_data.data, current_user.get_bot(), current_user.get_user()
    )
    return {"message": "Training Example removed successfully!"}


@router.get("/response/{utterance}", response_model=Response)
async def get_responses(
    utterance: str, current_user: User = Depends(auth.get_current_user)
):
    return {
        "data": list(mongo_processor.get_response(utterance, current_user.get_bot()))
    }


@router.post("/response/{utterance}", response_model=Response)
async def add_responses(
    request_data: TextData,
    utterance: str,
    current_user: User = Depends(auth.get_current_user),
):
    id = mongo_processor.add_text_response(
        request_data.data, utterance, current_user.get_bot(), current_user.get_user()
    )
    return {"message": "Response added successfully!", "data": {"_id": id}}


@router.delete("/response", response_model=Response)
async def remove_responses(
    request_data: TextData, current_user: User = Depends(auth.get_current_user)
):
    mongo_processor.remove_document(
        Responses, request_data.data, current_user.get_bot(), current_user.get_user()
    )
    return {
        "message": "Response removed successfully!",
    }


@router.post("/stories", response_model=Response)
async def add_stories(
    story: StoryRequest, current_user: User = Depends(auth.get_current_user)
):
    return {
        "message": "Story added successfully",
        "data": {
            "_id": mongo_processor.add_story(
                story.name,
                story.get_events(),
                current_user.get_bot(),
                current_user.get_user(),
            )
        },
    }


@router.get("/stories", response_model=Response)
async def get_stories(current_user: User = Depends(auth.get_current_user)):
    return {"data": list(mongo_processor.get_stories(current_user.get_bot()))}


@router.get("/utterance_from_intent/{intent}", response_model=Response)
async def get_story_from_intent(
    intent: str, current_user: User = Depends(auth.get_current_user)
):
    return {
        "data": mongo_processor.get_utterance_from_intent(
            intent, current_user.get_bot()
        )
    }


@router.post("/chat", response_model=Response)
async def chat(
    request_data: TextData, current_user: User = Depends(auth.get_current_user)
):
    model = AgentProcessor.get_agent(current_user.get_bot())
    response = await model.handle_text(request_data.data)
    return {"data": {"response": response[0]["text"] if response else None}}


@router.post("/train", response_model=Response)
async def train(current_user: User = Depends(auth.get_current_user)):
    model_file = await train_model_from_mongo(current_user.get_bot())
    return {"data": {"file": model_file}, "message": "Model trained successfully"}


@router.post("/deploy", response_model=Response)
async def deploy(current_user: User = Depends(auth.get_current_user)):
    endpoint = mongo_processor.get_endpoints(current_user.get_bot(),raise_exception=False)
    return {"message": Utility.deploy_model(endpoint, current_user.get_bot())}
