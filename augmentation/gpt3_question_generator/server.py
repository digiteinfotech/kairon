from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi import FastAPI, HTTPException
from fastapi import Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger as logging
from kairon.api.models import (User, Response)
from kairon.api.auth import Authentication
from kairon.utils import Utility
from .gpt_generator import GPT3QuestionGenerator
from .models import Response, AugmentationRequest
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
    Utility.load_evironment()
    connect(host=Utility.environment['database']["url"])


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


@app.post("/gpt/generate_questions", response_model=Response)
async def generate_questions(request_data: AugmentationRequest):

    try:
        gpt3_generator = GPT3QuestionGenerator(request_data)
        augmented_questions = gpt3_generator.augment_questions()
    except Exception as e:
        return {"message": str(e)}

    return {"data": {"questions": augmented_questions}}

if __name__ == "main":
    uvicorn.run(app)
