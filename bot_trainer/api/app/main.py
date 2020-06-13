import logging

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from mongoengine import connect, disconnect
from mongoengine.errors import (
    DoesNotExist,
    ValidationError,
    OperationError,
    NotRegistered,
    InvalidDocumentError,
    LookUpError,
    MultipleObjectsReturned,
    InvalidQueryError,
)
from starlette.exceptions import HTTPException as StarletteHTTPException

from bot_trainer.exceptions import AppException
from bot_trainer.utils import Utility
from .routers import auth, bot, augment, history, user, account
from bot_trainer.api.models import Response
from bot_trainer.api.processor import AccountProcessor
from fastapi.middleware.cors import CORSMiddleware
from pymongo.errors import PyMongoError
from secure import SecureHeaders

secure_headers = SecureHeaders()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["content-disposition"]
)


@app.middleware("http")
async def add_secure_headers(request: Request, call_next):
    response = await call_next(request)
    secure_headers.starlette(response)
    return response


@app.on_event("startup")
async def startup():
    """ MongoDB is connected on the bot trainer startup """
    connect(Utility.environment["mongo_db"], host=Utility.environment["mongo_url"])
    await AccountProcessor.default_account_setup()


@app.on_event("shutdown")
async def shutdown():
    """ MongoDB is disconnected when bot trainer is shut down """
    disconnect()


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


@app.exception_handler(AssertionError)
async def http_exception_handler(request, exc):
    """ This function logs the Assertion error detected and returns the
        appropriate message and details of the error """
    logging.exception(exc)
    return JSONResponse(
        Response(
            success=False, error_code=422, message=str(exc)
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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    """ logs the RequestValidationError detected and returns the
        appropriate message and details of the error """
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(DoesNotExist)
async def app_does_not_exist_exception_handler(request, exc):
    """ logs the DoesNotExist error detected and returns the
        appropriate message and details of the error """
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(PyMongoError)
async def pymongo_exception_handler(request, exc):
    """ logs the PyMongoError detected and returns the
        appropriate message and details of the error """
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(ValidationError)
async def app_validation_exception_handler(request, exc):
    """ logs the ValidationError detected and returns the
        appropriate message and details of the error """
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(OperationError)
async def mongoengine_operation_exception_handler(request, exc):
    """ logs the OperationError detected and returns the
            appropriate message and details of the error """
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(NotRegistered)
async def mongoengine_notregistered_exception_handler(request, exc):
    """ logs the NotRegistered error detected and returns the
            appropriate message and details of the error """
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(InvalidDocumentError)
async def mongoengine_invalid_document_exception_handler(request, exc):
    """ logs the InvalidDocumentError detected and returns the
            appropriate message and details of the error """
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(LookUpError)
async def mongoengine_lookup_exception_handler(request, exc):
    """ logs the LookUpError detected and returns the
            appropriate message and details of the error """
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(MultipleObjectsReturned)
async def mongoengine_multiple_objects_exception_handler(request, exc):
    """ logs the MultipleObjectsReturned error detected and returns the
            appropriate message and details of the error """
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(InvalidQueryError)
async def mongoengine_invalid_query_exception_handler(request, exc):
    """ logs the InvalidQueryError detected and returns the
            appropriate message and details of the error """
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(AppException)
async def app_exception_handler(request, exc):
    """ logs the AppException error detected and returns the
            appropriate message and details of the error """
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


app.include_router(auth.router, prefix="/api/auth")
app.include_router(account.router, prefix="/api/account", tags=["Account"])
app.include_router(user.router, prefix="/api/user", tags=["User"])
app.include_router(bot.router, prefix="/api/bot", tags=["Bot"])
app.include_router(augment.router, prefix="/api/augment", tags=["Augmentation"])
app.include_router(history.router, prefix="/api/history", tags=["History"])
