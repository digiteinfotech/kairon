from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi import FastAPI, HTTPException
from fastapi import Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger as logging
from kairon.api.models import (User, Response)
from kairon.api.auth import Authentication

from .gpt_generator import GPT3QuestionGenerator
from .models import GPTAddKeyRequest, Response, AugmentationRequest
from .gpt_processor.gpt_processors import GPT3ApiKey
import uvicorn
from mongoengine import connect

auth = Authentication()
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    connect(host="mongodb://192.168.101.148:27019/conversations")


@app.exception_handler(StarletteHTTPException)
async def startlette_exception_handler(request, exc):
    """ This function logs the Starlette HTTP error detected and returns the
        appropriate message and details of the error """
    logging.exception(exc)

    return JSONResponse(
        Response(
            success=False, error_code=exc.status_code, message=str(exc.detail)
        ).dict()
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """ This function logs the HTTP error detected and returns the
            appropriate message and details of the error """
    logging.exception(exc)
    return JSONResponse(
        Response(
            success=False, error_code=exc.status_code, message=str(exc.detail)
        ).dict()
    )


@app.post("/gpt/key", response_model=Response)
async def add_key(request_data: GPTAddKeyRequest, current_user: User = Depends(auth.get_current_user)):

    try:
        GPT3ApiKey.add_gpt_key(user=current_user.email, api_key=request_data.key)
    except Exception as e:
        return {"message": str(e)}

    return {"message": "Key added successfully"}


@app.post("/gpt/generate_questions", response_model=Response)
async def generate_questions(request_data: AugmentationRequest, current_user: User = Depends(auth.get_current_user)):

    try:
        gpt3_generator = GPT3QuestionGenerator(request_data, current_user.email)
        augmented_questions = gpt3_generator.augment_questions()
    except Exception as e:
        return {"message": str(e)}

    return {"data": {"questions": augmented_questions}}

if __name__ == "main":
    uvicorn.run(app)
