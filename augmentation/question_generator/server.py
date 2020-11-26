from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger as logging
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from .generator import QuestionGenerator


class Response(BaseModel):
    """ This class defines the variables (and their types) that will be defined in the response
        message when a HTTP error is detected """

    success: bool = True
    message: str = None
    data: Any
    error_code: int = 0


class Request(BaseModel):
    """ This class defines the variables (and their types) that will be defined in the request
            message"""
    data: str


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


@app.post("/questions", response_model=Response)
async def questions(request_data: Request):
    """Generates variations for given list of passage"""
    response = QuestionGenerator.generate(request_data.data)
    return {"data": {"questions": response}}
