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
)


@app.middleware("http")
async def add_secure_headers(request: Request, call_next):
    response = await call_next(request)
    secure_headers.starlette(response)
    return response


@app.on_event("startup")
async def startup():
    connect(Utility.environment["mongo_db"], host=Utility.environment["mongo_url"])
    await AccountProcessor.default_account_setup()


@app.on_event("shutdown")
async def shutdown():
    disconnect()


@app.exception_handler(StarletteHTTPException)
async def startlette_exception_handler(request, exc):
    logging.exception(exc)

    return JSONResponse(
        Response(
            success=False, error_code=exc.status_code, message=str(exc.detail)
        ).dict()
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    logging.exception(exc)
    return JSONResponse(
        Response(
            success=False, error_code=exc.status_code, message=str(exc.detail)
        ).dict()
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(DoesNotExist)
async def app_does_not_exist_exception_handler(request, exc):
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(PyMongoError)
async def pymongo_exception_handler(request, exc):
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(ValidationError)
async def app_validation_exception_handler(request, exc):
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(OperationError)
async def mongoengine_operation_exception_handler(request, exc):
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(NotRegistered)
async def mongoengine_notregistered_exception_handler(request, exc):
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(InvalidDocumentError)
async def mongoengine_invalid_document_exception_handler(request, exc):
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(LookUpError)
async def mongoengine_lookup_exception_handler(request, exc):
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(MultipleObjectsReturned)
async def mongoengine_multiple_objects_exception_handler(request, exc):
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(InvalidQueryError)
async def mongoengine_invalid_query_exception_handler(request, exc):
    logging.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(AppException)
async def app_exception_handler(request, exc):
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
