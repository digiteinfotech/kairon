import copy
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from jwt import PyJWTError
from loguru import logger
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
from pymongo.errors import PyMongoError
from secure import StrictTransportSecurity, ReferrerPolicy, ContentSecurityPolicy, XContentTypeOptions, Server, \
    CacheControl, Secure, PermissionsPolicy
from starlette.exceptions import HTTPException as StarletteHTTPException

from kairon.api.app.routers import auth, augment, history, user, account, idp, system
from kairon.api.app.routers.bot import action, bot, agents, secrets, multilingual, metric, data, \
    channels, custom_widgets, integrations
from kairon.api.models import Response
from kairon.exceptions import AppException
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.utils import Utility
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
)
cache_value = CacheControl().must_revalidate()
content = XContentTypeOptions()
server = Server().set("Secure")
permissions_value = (
    PermissionsPolicy().accelerometer().autoplay().camera().document_domain().encrypted_media().fullscreen().vibrate()
        .geolocation().gyroscope().magnetometer().microphone().midi().payment().picture_in_picture().sync_xhr().usb()
)
secure_headers = Secure(
    server=server,
    csp=csp,
    hsts=hsts,
    referrer=referrer,
    permissions=permissions_value,
    cache=cache_value,
    content=content
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """ MongoDB is connected on the bot trainer startup """
    config: dict = Utility.mongoengine_connection(Utility.environment['database']["url"])
    connect(**config)
    await AccountProcessor.default_account_setup()
    AccountProcessor.load_system_properties()
    yield
    disconnect()


app = FastAPI(lifespan=lifespan)
allowed_origins = Utility.environment['cors']['origin']
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["content-disposition"],
)
app.add_middleware(GZipMiddleware)
instrument_fastapi(app)


@app.middleware("http")
async def add_secure_headers(request: Request, call_next):
    """add security headers"""
    response = await call_next(request)
    secure_headers.framework.fastapi(response)
    response.headers['Cross-Origin-Embedder-Policy'] = 'require-corp'
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
    response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    requested_origin = request.headers.get("origin")
    response.headers["Access-Control-Allow-Origin"] = requested_origin if requested_origin is not None else allowed_origins[0]
    if request.url.path == "/redoc":
        custom_csp = copy.deepcopy(csp)
        custom_csp.worker_src("blob:")
        secure_headers.csp = custom_csp
        secure_headers.framework.fastapi(response)
        secure_headers.csp = csp
    return response


@app.exception_handler(StarletteHTTPException)
async def startlette_exception_handler(request, exc):
    """ This function logs the Starlette HTTP error detected and returns the
        appropriate message and details of the error """

    return JSONResponse(
        Response(
            success=False, error_code=exc.status_code, message=str(exc.detail)
        ).dict()
    )


@app.exception_handler(AssertionError)
async def http_exception_handler(request, exc):
    """ This function logs the Assertion error detected and returns the
        appropriate message and details of the error """
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    """ logs the RequestValidationError detected and returns the
        appropriate message and details of the error """
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=exc.errors()).dict()
    )


@app.exception_handler(DoesNotExist)
async def app_does_not_exist_exception_handler(request, exc):
    """ logs the DoesNotExist error detected and returns the
        appropriate message and details of the error """
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(PyMongoError)
async def pymongo_exception_handler(request, exc):
    """ logs the PyMongoError detected and returns the
        appropriate message and details of the error """
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(ValidationError)
async def app_validation_exception_handler(request, exc):
    """ logs the ValidationError detected and returns the
        appropriate message and details of the error """
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(OperationError)
async def mongoengine_operation_exception_handler(request, exc):
    """ logs the OperationError detected and returns the
            appropriate message and details of the error """
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(NotRegistered)
async def mongoengine_notregistered_exception_handler(request, exc):
    """ logs the NotRegistered error detected and returns the
            appropriate message and details of the error """
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(InvalidDocumentError)
async def mongoengine_invalid_document_exception_handler(request, exc):
    """ logs the InvalidDocumentError detected and returns the
            appropriate message and details of the error """
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(LookUpError)
async def mongoengine_lookup_exception_handler(request, exc):
    """ logs the LookUpError detected and returns the
            appropriate message and details of the error """
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(MultipleObjectsReturned)
async def mongoengine_multiple_objects_exception_handler(request, exc):
    """ logs the MultipleObjectsReturned error detected and returns the
            appropriate message and details of the error """
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(InvalidQueryError)
async def mongoengine_invalid_query_exception_handler(request, exc):
    """ logs the InvalidQueryError detected and returns the
            appropriate message and details of the error """
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(PyJWTError)
async def pyjwt_exception_handler(request, exc):
    """ logs the AppException error detected and returns the
            appropriate message and details of the error """
    logger.exception(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.exception_handler(AppException)
async def app_exception_handler(request, exc):
    """ logs the AppException error detected and returns the
            appropriate message and details of the error """
    logger.info(exc)
    return JSONResponse(
        Response(success=False, error_code=422, message=str(exc)).dict()
    )


@app.get("/", response_model=Response)
def index():
    return {"message": "hello"}


@app.get("/healthcheck", response_model=Response)
def healthcheck():
    return {"message": "health check ok"}


app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(account.router, prefix="/api/account", tags=["Account"])
app.include_router(user.router, prefix="/api/user", tags=["User"])
app.include_router(bot.router, prefix="/api/bot/{bot}", tags=["Bot"])
app.include_router(action.router, prefix="/api/bot/{bot}/action", tags=["Action"])
app.include_router(agents.router, prefix="/api/bot/{bot}/agents", tags=["LiveAgent"])
app.include_router(channels.router, prefix="/api/bot/{bot}/channels", tags=["Channels"])
app.include_router(secrets.router, prefix="/api/bot/{bot}/secrets", tags=["KeyVault"])
app.include_router(multilingual.router, prefix="/api/bot/{bot}/multilingual", tags=["Multilingual"])
app.include_router(metric.router, prefix="/api/bot/{bot}/metric", tags=["Metric"])
app.include_router(augment.router, prefix="/api/augment", tags=["Augmentation"])
app.include_router(history.router, prefix="/api/history/{bot}", tags=["History"])
app.include_router(idp.router, prefix="/api/idp", tags=["SSO", "IDP"])
app.include_router(system.router, prefix="/api/system", tags=["Application"])
app.include_router(data.router, prefix="/api/bot/{bot}/data", tags=["File Upload/Download"])
app.include_router(custom_widgets.router, prefix="/api/bot/{bot}/widgets", tags=["Custom analytical widgets"])
app.include_router(integrations.router, prefix="/api/bot/integration", tags=["Data Integrations"])
