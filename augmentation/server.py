from fastapi import FastAPI, HTTPException
from .generator import QuestionGenerator
from pydantic import BaseModel
from typing import Any, List, Text
import logging
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware


class Response(BaseModel):
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
    logging.exception(exc)

    return JSONResponse(
        Response(success=False, error_code=exc.status_code, message=str(exc.detail)).dict()
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=exc.status_code, message=str(exc.detail)).dict()
    )

@app.post("/questions", response_model=Response)
async def chat(
    request_data: List[Text]
):
    response = await QuestionGenerator.generateQuestions(request_data)
    return {"data": {"questions": response}}