import requests
from fastapi import APIRouter
from fastapi import Depends

from kairon.shared.auth import Authentication
from kairon.api.models import Response, ParaphrasesRequest, TextData, GPTRequest
from kairon.shared.models import User
from kairon.shared.utils import Utility
from kairon.shared.data.utils import DataUtility

router = APIRouter()


@router.post("/paraphrases", response_model=Response)
async def paraphrases(
        request_data: ParaphrasesRequest, current_user: User = Depends(Authentication.get_current_user)
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
        request_data: TextData, current_user: User = Depends(Authentication.get_current_user)
):
    """
    Generates question from text or url
    """
    response = requests.post(
        Utility.environment["augmentation"]["question_generation_url"], json=request_data.dict()
    )
    return response.json()


@router.post("/paraphrases/gpt", response_model=Response)
async def gpt_paraphrases(request_data: GPTRequest,  current_user: User = Depends(Authentication.get_current_user)):
    """Generates variations for given list of sentences/questions using GPT3"""
    response = requests.post(
        Utility.environment["augmentation"]["paraphrase_gpt_url"], json=request_data.dict()
    )
    return response.json()
