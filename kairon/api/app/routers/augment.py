import requests
from fastapi import APIRouter, Security, UploadFile, File
from starlette.background import BackgroundTasks

from kairon.events.events import EventsTrigger
from kairon.shared.auth import Authentication
from kairon.api.models import Response, ParaphrasesRequest, TextData, GPTRequest, QnAGeneratorRequest
from kairon.shared.constants import DESIGNER_ACCESS, TESTER_ACCESS
from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.data.training_data_generation_processor import TrainingDataGenerationProcessor
from kairon.shared.models import User
from kairon.shared.utils import Utility
from kairon.shared.data.utils import DataUtility

router = APIRouter()


@router.post("/paraphrases", response_model=Response)
async def paraphrases(
        request_data: ParaphrasesRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Generates other similar text by augmenting original text
    """
    plain_text_data = [
        DataUtility.extract_text_and_entities(data)[0] for data in request_data.data
    ]
    response = requests.post(
        Utility.environment["augmentation"]["paraphrase_url"], json=plain_text_data
    )
    return response.json()


@router.post("/questions", response_model=Response)
async def questions(
        request_data: TextData,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Generates question from text or url
    """
    response = requests.post(
        Utility.environment["augmentation"]["question_generation_url"], json=request_data
    )
    return response.json()


@router.post("/paraphrases/gpt", response_model=Response)
async def gpt_paraphrases(
        request_data: GPTRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """Generates variations for given list of sentences/questions using GPT3"""
    response = requests.post(
        Utility.environment["augmentation"]["paraphrase_gpt_url"], json=request_data.dict()
    )
    return response.json()


@router.post("/generate/data/file/upload", response_model=Response)
async def upload_data_generation_file(
    background_tasks: BackgroundTasks,
    doc: UploadFile = File(...),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Uploads document for training data generation and triggers event for intent creation
    """
    TrainingDataGenerationProcessor.is_in_progress(current_user.get_bot())
    TrainingDataGenerationProcessor.check_data_generation_limit(current_user.get_bot())
    file_path = await Utility.upload_document(doc)
    TrainingDataGenerationProcessor.set_status(
        bot=current_user.get_bot(),
        user=current_user.get_user(), status=EVENT_STATUS.INITIATED.value,
        document_path=file_path, generator_type='document'
    )
    token = Authentication.create_access_token(data={"sub": current_user.email})
    background_tasks.add_task(
        DataUtility.trigger_data_generation_event, current_user.get_bot(), current_user.get_user(), token
    )
    return {"message": "File uploaded successfully and training data generation has begun"}


@router.post("/generate/data/website", response_model=Response)
async def generate_data_from_website(
    background_tasks: BackgroundTasks, request: QnAGeneratorRequest,
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Scrapes website data and generates question and answer pairs from it.
    """
    TrainingDataGenerationProcessor.is_in_progress(current_user.get_bot())
    TrainingDataGenerationProcessor.check_data_generation_limit(current_user.get_bot())
    background_tasks.add_task(
        EventsTrigger.trigger_qna_generator_for_website, current_user.get_bot(),
        current_user.get_user(), request.url, request.max_depth
    )
    return {"message": "Training data generation initiated. Check logs."}


@router.get("/history/generate/data", response_model=Response)
async def get_train_data_history(
        running_event: bool = False,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS),
):
    """
    Fetches File Data Generation history, when and who initiated the process
    """
    if running_event:
        log = TrainingDataGenerationProcessor.fetch_latest_workload(current_user.get_bot(), current_user.get_user())
    else:
        log = TrainingDataGenerationProcessor.get_training_data_generator_history(current_user.get_bot())
    return {"data": log}
