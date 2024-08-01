from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from mongoengine import connect, disconnect

from kairon.shared.account.processor import AccountProcessor
from kairon.shared.utils import Utility
Utility.load_environment()

from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from secure import StrictTransportSecurity, ReferrerPolicy, ContentSecurityPolicy, XContentTypeOptions, Server, \
    CacheControl, Secure, PermissionsPolicy

from kairon.api.models import Response
from kairon.async_callback.router import pyscript_callback
from kairon.shared.otel import instrument_fastapi


hsts = StrictTransportSecurity().include_subdomains().preload().max_age(31536000)
referrer = ReferrerPolicy().no_referrer()
csp = (
    ContentSecurityPolicy().default_src("'self'")
        .frame_ancestors("'self'")
        .form_action("'self'")
        .base_uri("'self'")
        .connect_src("'self'" "api.spam.com")
        .frame_src("'self'")
        .img_src("'self'", "static.spam.com")
)
cache_value = CacheControl().must_revalidate()
content = XContentTypeOptions()
server = Server().set("Secure")
permissions_value = (
    PermissionsPolicy().accelerometer("").autoplay("").camera("").document_domain("").encrypted_media("")
        .fullscreen("").geolocation("").gyroscope("").magnetometer("").microphone("").midi("").payment("")
        .picture_in_picture("").sync_xhr("").usb("").geolocation("self", "'spam.com'").vibrate()
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["content-disposition"],
)
app.add_middleware(GZipMiddleware)
instrument_fastapi(app)


@app.middleware("http")
async def add_secure_headers(request: Request, call_next):
    """Add security headers."""
    response = await call_next(request)
    secure_headers.framework.fastapi(response)
    return response


@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        logger.exception(exc)

        return JSONResponse(
            Response(
                success=False, error_code=422, message=str(exc)
            ).dict()
        )


@app.get("/", response_model=Response)
def index():
    return {"message": "Running Async Callback Server"}


@app.get("/healthcheck", response_model=Response)
def healthcheck():
    return {"message": "health check ok"}


app.include_router(pyscript_callback.router)

