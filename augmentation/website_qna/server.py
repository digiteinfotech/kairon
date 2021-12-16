from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Generator, List, Text
from loguru import logger as logging
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from utils.generator import QuestionGenerator
from utils.web_scraper import WEB_SCRAPPER
from utils.WebsiteQAGenerator import WebsiteQAGenerator

import uvicorn


class Response(BaseModel):
    """ This class defines the variables (and their types) that will be defined in the response
        message when a HTTP error is detected """

    success: bool = True
    message: str = None
    data: Any
    error_code: int = 0

class websiteQAData(BaseModel):
    url: str
    max_pages: int


class TextData(BaseModel):
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

@app.post("/get_qna/")
async def create_item(item: websiteQAData):
    response = WebsiteQAGenerator.get_qa_data(item.url,item.max_pages)
    return {"data": {"QnA": response}}

@app.post("/questions/")
async def create_item(item: TextData):
    response = QuestionGenerator.generate(item.data)
    return {"data": {"questions": response}}


@app.post("/scrape/")
async def create_item(item: websiteQAData):
    response = WEB_SCRAPPER.scrape_pages(item.url,item.max_pages)
    return {"data": {"pages": response}}



if __name__ == "main":
    uvicorn.run(app)