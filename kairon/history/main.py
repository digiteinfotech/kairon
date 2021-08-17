import logging
from time import time

from elasticapm.contrib.starlette import ElasticAPM
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.security.utils import get_authorization_scheme_param
from loguru import logger
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
from pymongo.errors import PyMongoError
from secure import SecureHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException

from kairon import Utility
from kairon.api.models import Response
from kairon.exceptions import AppException
from kairon.history.router import metrics, conversations, trends
from kairon.history.utils import HistoryUtils

logging.basicConfig(level="DEBUG")
secure_headers = SecureHeaders()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["content-disposition"],
)
app.add_middleware(GZipMiddleware)
HistoryUtils.load_environment()
Utility.load_evironment()
apm_client = Utility.initiate_apm_client()
if apm_client:
    app.add_middleware(ElasticAPM, client=apm_client)


@app.middleware("http")
async def add_secure_headers(request: Request, call_next):
    """Add security headers."""
    response = await call_next(request)
    secure_headers.starlette(response)
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Logging request calls."""
    authorization: str = request.headers.get("Authorization")
    _, param = get_authorization_scheme_param(authorization)
    start_time = time()

    response = await call_next(request)

    process_time = (time() - start_time) * 1000
    formatted_process_time = "{0:.2f}".format(process_time)
    logger.info(
        f"rid={param} request path={request.url.path} completed_in={formatted_process_time}ms status_code={response.status_code}"
    )

    return response


@app.exception_handler(StarletteHTTPException)
async def startlette_exception_handler(request, exc):

    """Error handler for StarletteHTTPException.

    This function logs the Starlette HTTP error detected and returns the
    appropriate message and details of the error.
    """
    logger.debug(exc)

    return JSONResponse(
        Response(
            success=False, error_code=exc.status_code, message=str(exc.detail)
        ).dict()
    )


@app.exception_handler(AssertionError)
async def assertion_error_handler(request, exc):

    """Error handler for AssertionError.

    This function logs the Assertion error detected and returns the
    appropriate message and details of the error.
    """
    logger.debug(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):

    """Error handler for HTTPException.

    This function logs the HTTP error detected and returns the
    appropriate message and details of the error.
    """
    logger.debug(exc)
    return JSONResponse(
        Response(
            success=False, error_code=exc.status_code, message=str(exc.detail)
        ).dict()
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):

    """Error handler for RequestValidationError.

     Logs the RequestValidationError detected and returns the
     appropriate message and details of the error.
     """
    logger.debug(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=exc.errors()).dict()
    )


@app.exception_handler(DoesNotExist)
async def app_does_not_exist_exception_handler(request, exc):

    """Error handler for DoesNotExist errors.

    Logs the DoesNotExist error detected and returns the
    appropriate message and details of the error.
    """
    logger.debug(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(PyMongoError)
async def pymongo_exception_handler(request, exc):

    """Error handler for PyMongoError errors.

     Logs the PyMongoError detected and returns the
     appropriate message and details of the error.
     """
    logger.debug(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(ValidationError)
async def app_validation_exception_handler(request, exc):

    """Error handler for ValidationError.

     Logs the ValidationError detected and returns the
    appropriate message and details of the error.
    """
    logger.debug(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(OperationError)
async def mongoengine_operation_exception_handler(request, exc):

    """Error handler for OperationError.

     Logs the OperationError detected and returns the
     appropriate message and details of the error.
     """
    logger.debug(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(NotRegistered)
async def mongoengine_notregistered_exception_handler(request, exc):

    """Error handler for NotRegistered errors.

     Logs the NotRegistered error detected and returns the
    appropriate message and details of the error.
    """
    logger.debug(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(InvalidDocumentError)
async def mongoengine_invalid_document_exception_handler(request, exc):

    """Error handler for InvalidDocumentError.

     Logs the InvalidDocumentError detected and returns the
     appropriate message and details of the error.
     """
    logger.debug(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(LookUpError)
async def mongoengine_lookup_exception_handler(request, exc):

    """Error handler for LookUpError.

     Logs the LookUpError detected and returns the
    appropriate message and details of the error.
    """
    logger.debug(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(MultipleObjectsReturned)
async def mongoengine_multiple_objects_exception_handler(request, exc):

    """Error handler for MultipleObjectsReturned.

     Logs the MultipleObjectsReturned error detected and returns the
    appropriate message and details of the error.
    """
    logger.debug(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(InvalidQueryError)
async def mongoengine_invalid_query_exception_handler(request, exc):

    """Error handler for InvalidQueryError.

     Logs the InvalidQueryError detected and returns the
    appropriate message and details of the error.
    """
    logger.debug(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(AppException)
async def app_exception_handler(request, exc):

    """Error handler for AppException errors.

     Logs the AppException error detected and returns the
    appropriate message and details of the error.
    """
    logger.debug(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.get("/", response_model=Response)
def index():
    return {"message": "hello"}


app.include_router(metrics.router, prefix="/api/history/{bot}/metrics", tags=["Metrics"])
app.include_router(conversations.router, prefix="/api/history/{bot}/conversations", tags=["Conversations"])
app.include_router(trends.router, prefix="/api/history/{bot}/trends", tags=["Trends"])
