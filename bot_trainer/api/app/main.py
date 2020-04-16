import logging

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from mongoengine import connect, disconnect
from mongoengine.errors import DoesNotExist, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from bot_trainer.exceptions import AppException
from bot_trainer.utils import Utility
from .routers import auth, bot

app = FastAPI()


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
        {"success": False, "error_code": exc.status_code, "message": str(exc.detail)}
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    logging.exception(exc)
    return JSONResponse(
        {"success": False, "error_code": exc.status_code, "message": str(exc.detail)}
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    logging.exception(exc)
    exception_str = str(exc)
    last_index = exception_str.find("(")
    return JSONResponse(
        {
            "success": False,
            "error_code": 400,
            "message": exception_str[:last_index].strip(),
        }
    )


@app.exception_handler(DoesNotExist)
async def app_does_not_exist_exception_handler(request, exc):
    logging.exception(exc)
    return JSONResponse({"success": False, "error_code": 400, "message": str(exc)})


@app.exception_handler(ValidationError)
async def app_validation_exception_handler(request, exc):
    logging.exception(exc)
    return JSONResponse({"success": False, "error_code": 400, "message": str(exc)})


@app.exception_handler(AppException)
async def app_exception_handler(request, exc):
    logging.exception(exc)
    return JSONResponse({"success": False, "error_code": 400, "message": str(exc)})


app.include_router(auth.router, prefix="/api/auth")
app.include_router(bot.router, prefix="/api/bot")
app.include_router(bot.router, prefix="/api/augment")
