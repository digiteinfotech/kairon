import logging

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from mongoengine import connect, disconnect
from mongoengine.errors import DoesNotExist, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from bot_trainer.exceptions import AppException
from bot_trainer.utils import Utility
from .routers import auth, bot, augment, history
from bot_trainer.api.models import Response
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def start_up():
    connect(Utility.environment["mongo_db"], host=Utility.environment["mongo_url"])


@app.on_event("shutdown")
async def start_up():
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


@app.exception_handler(ValidationError)
async def app_validation_exception_handler(request, exc):
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
app.include_router(bot.router, prefix="/api/bot", tags=["Bot"])
app.include_router(augment.router, prefix="/api/augment", tags=["Augmentation"])
app.include_router(history.router, prefix="/api/history", tags=["History"])
