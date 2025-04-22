from loguru import logger as logging
from time import time

from fastapi import FastAPI
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.security.utils import get_authorization_scheme_param
from jwt import PyJWTError
from loguru import logger
from mongoengine import connect
from mongoengine import disconnect
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
from rasa_sdk import utils
from rasa_sdk.interfaces import ActionExecutionRejection, ActionNotFoundException
from secure import (
    StrictTransportSecurity,
    ReferrerPolicy,
    ContentSecurityPolicy,
    XContentTypeOptions,
    Server,
    CacheControl,
    Secure,
    PermissionsPolicy,
)
from starlette.exceptions import HTTPException as StarletteHTTPException

from kairon.actions.handlers.action import ActionHandler
from kairon.api.models import Response
from kairon.exceptions import AppException
from ..shared.utils import Utility
from ..shared.account.processor import AccountProcessor
from contextlib import asynccontextmanager
from kairon.shared.otel import instrument_fastapi

hsts = StrictTransportSecurity().include_subdomains().preload().max_age(31536000)
referrer = ReferrerPolicy().no_referrer()
csp = (
    ContentSecurityPolicy()
    .default_src("'self'")
    .frame_ancestors("'self'")
    .form_action("'self'")
    .base_uri("'self'")
    .connect_src("'self'")
    .frame_src("'self'")
    .style_src("'self'", "https:", "'unsafe-inline'")
    .img_src("'self'", "https:")
    .script_src("'self'", "https:", "'unsafe-inline'")
    .worker_src("'self'", "blob:")
)
cache_value = CacheControl().must_revalidate()
content = XContentTypeOptions()
server = Server().set("Secure")
permissions_value = (
    PermissionsPolicy()
    .accelerometer()
    .autoplay()
    .camera()
    .document_domain()
    .encrypted_media()
    .fullscreen()
    .vibrate()
    .geolocation()
    .gyroscope()
    .magnetometer()
    .microphone()
    .midi()
    .payment()
    .picture_in_picture()
    .sync_xhr()
    .usb()
)
secure_headers = Secure(
    server=server,
    csp=csp,
    hsts=hsts,
    referrer=referrer,
    permissions=permissions_value,
    cache=cache_value,
    content=content,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """MongoDB is connected on the bot trainer startup"""
    config: dict = Utility.mongoengine_connection(
        Utility.environment["database"]["url"]
    )
    connect(**config)
    AccountProcessor.load_system_properties()
    yield
    disconnect()


action = FastAPI(lifespan=lifespan)
Utility.load_environment()
Utility.load_email_configuration()
allowed_origins = Utility.environment["cors"]["origin"]
action.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["content-disposition"],
)
action.add_middleware(GZipMiddleware)
instrument_fastapi(action)


@action.middleware("http")
async def add_secure_headers(request: Request, call_next):
    """add security headers"""
    response = await call_next(request)
    secure_headers.framework.fastapi(response)
    response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    requested_origin = request.headers.get("origin")
    response.headers["Access-Control-Allow-Origin"] = (
        requested_origin if requested_origin is not None else allowed_origins[0]
    )
    return response


@action.middleware("http")
async def log_requests(request: Request, call_next):
    """logging request calls"""
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


@action.exception_handler(StarletteHTTPException)
async def startlette_exception_handler(request, exc):
    """This function logs the Starlette HTTP error detected and returns the
    appropriate message and details of the error"""
    logger.exception(exc)

    return JSONResponse(
        Response(
            success=False, error_code=exc.status_code, message=str(exc.detail)
        ).dict()
    )


@action.exception_handler(AssertionError)
async def http_exception_handler(request, exc):
    """This function logs the Assertion error detected and returns the
    appropriate message and details of the error"""
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@action.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    """logs the RequestValidationError detected and returns the
    appropriate message and details of the error"""
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=exc.errors()).dict()
    )


@action.exception_handler(DoesNotExist)
async def app_does_not_exist_exception_handler(request, exc):
    """logs the DoesNotExist error detected and returns the
    appropriate message and details of the error"""
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@action.exception_handler(PyMongoError)
async def pymongo_exception_handler(request, exc):
    """logs the PyMongoError detected and returns the
    appropriate message and details of the error"""
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@action.exception_handler(ValidationError)
async def app_validation_exception_handler(request, exc):
    """logs the ValidationError detected and returns the
    appropriate message and details of the error"""
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@action.exception_handler(OperationError)
async def mongoengine_operation_exception_handler(request, exc):
    """logs the OperationError detected and returns the
    appropriate message and details of the error"""
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@action.exception_handler(NotRegistered)
async def mongoengine_notregistered_exception_handler(request, exc):
    """logs the NotRegistered error detected and returns the
    appropriate message and details of the error"""
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@action.exception_handler(InvalidDocumentError)
async def mongoengine_invalid_document_exception_handler(request, exc):
    """logs the InvalidDocumentError detected and returns the
    appropriate message and details of the error"""
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@action.exception_handler(LookUpError)
async def mongoengine_lookup_exception_handler(request, exc):
    """logs the LookUpError detected and returns the
    appropriate message and details of the error"""
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@action.exception_handler(MultipleObjectsReturned)
async def mongoengine_multiple_objects_exception_handler(request, exc):
    """logs the MultipleObjectsReturned error detected and returns the
    appropriate message and details of the error"""
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@action.exception_handler(InvalidQueryError)
async def mongoengine_invalid_query_exception_handler(request, exc):
    """logs the InvalidQueryError detected and returns the
    appropriate message and details of the error"""
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@action.exception_handler(PyJWTError)
async def pyjwt_exception_handler(request, exc):
    """logs the AppException error detected and returns the
    appropriate message and details of the error"""
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@action.exception_handler(AppException)
async def app_exception_handler(request, exc):
    """logs the AppException error detected and returns the
    appropriate message and details of the error"""
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@action.get("/")
async def get():
    return {"message": "Kairon Action Server Up and Running"}


@action.get("/healthcheck")
def healthcheck():
    return {"message": "health check ok"}


@action.post("/webhook")
async def webhook(request_json: dict):
    logging.debug(request_json)

    utils.check_version_compatibility(request_json.get("version"))
    try:
        result = await ActionHandler.process_actions(request_json)
        if result:
            result = JSONResponse(status_code=status.HTTP_200_OK, content=result)
        return result
    except ActionExecutionRejection as e:
        logger.debug(e)
        body = {"error": e.message, "action_name": e.action_name}
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=body)
    except ActionNotFoundException as e:
        logger.info(e)
        body = {"error": e.message, "action_name": e.action_name}
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=body)


async def main(scope, receive, send):
    await action.__call__(scope=scope, receive=receive, send=send)
