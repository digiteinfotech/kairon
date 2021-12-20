from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any
from loguru import logger as logging
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from utils.generator import QuestionGenerator
from utils.web_scraper import WebScraper
from utils.website_qna_generator import WebsiteQnAGenerator

import uvicorn


class Response(BaseModel):
    """This class defines the variables (and their types) that will be defined in the response message when a HTTP error is detected."""

    success: bool = True
    message: str = None
    data: Any
    error_code: int = 0

class websiteQnAData(BaseModel):
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
    """This function logs the Starlette HTTP error detected and returns the appropriate message and details of the error."""

    logging.exception(exc)

    return JSONResponse(
        Response(
            success=False, error_code=exc.status_code, message=str(exc.detail)
        ).dict()
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """This function logs the HTTP error detected and returns the appropriate message and details of the error."""
    logging.exception(exc)
    return JSONResponse(
        Response(
            success=False, error_code=exc.status_code, message=str(exc.detail)
        ).dict()
    )

@app.post("/get_qna/")
async def create_website_qna_item(item: websiteQnAData):
    """This function is used for generating QnA from website link."""
    response = WebsiteQnAGenerator.get_qa_data(item.url,item.max_pages)
    return {"data": {"QnA": response}}

@app.post("/questions/")
async def create_questions_item(item: TextData):
    """This function is used for generating Questions from given string."""
    response = QuestionGenerator.generate(item.data)
    return {"data": {"questions": response}}


@app.post("/scrape/")
async def create_scrape_item(item: websiteQnAData):
    """This function is used for scraping given website."""
    response = WebScraper.scrape_pages(item.url,item.max_pages)
    return {"data": {"pages": response}}



if __name__ == "main":
    uvicorn.run(app)