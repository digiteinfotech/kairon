from fastapi import FastAPI, HTTPException
from augmentation.paraphrase.paraphrasing import ParaPhrasing
from pydantic import BaseModel
from typing import Any, List, Text
from loguru import logger as logging
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from .gpt3.generator import GPT3ParaphraseGenerator
from .gpt3.models import GPTRequest
import uvicorn


class Response(BaseModel):
    """ This class defines the variables (and their types) that will be defined in the response
        message when a HTTP error is detected """

    success: bool = True
    message: str = None
    data: Any
    error_code: int = 0


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.post("/paraphrases", response_model=Response)
async def paraphrases(request_data: List[Text]):
    """Generates variations for given list of sentences/questions"""
    response = ParaPhrasing.paraphrases(request_data)
    return {"data": {"paraphrases": response}}


@app.post("/paraphrases/gpt", response_model=Response)
async def gpt_paraphrases(request_data: GPTRequest):
    """Generates variations for given list of sentences/questions using GPT3"""
    try:
        gpt3_generator = GPT3ParaphraseGenerator(request_data)
        augmented_questions = gpt3_generator.paraphrases()
    except Exception as e:
        return {"message": str(e), "success": False}

    return {"data": {"paraphrases": augmented_questions}}

if __name__ == "main":
    uvicorn.run(app)
