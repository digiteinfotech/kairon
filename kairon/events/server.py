import logging
from typing import Text

from elasticapm.contrib.starlette import ElasticAPM
from fastapi import FastAPI, Request, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from mongoengine import connect, disconnect
from secure import StrictTransportSecurity, ReferrerPolicy, ContentSecurityPolicy, XContentTypeOptions, Server, \
    CacheControl, Secure, PermissionsPolicy

from kairon.api.models import Response
from kairon.events.models import EventRequest
from kairon.events.scheduler.kscheduler import KScheduler
from kairon.events.utility import EventUtility
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.constants import EventClass
from kairon.shared.utils import Utility

logging.basicConfig(level="DEBUG")
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

app = FastAPI()
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
apm_client = Utility.initiate_fastapi_apm_client()

if apm_client:
    app.add_middleware(ElasticAPM, client=apm_client)


@app.middleware("http")
async def add_secure_headers(request: Request, call_next):
    """add security headers"""
    response = await call_next(request)
    secure_headers.framework.fastapi(response)
    response.headers['Cross-Origin-Embedder-Policy'] = 'require-corp'
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
    response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    requested_origin = request.headers.get("origin")
    response.headers["Access-Control-Allow-Origin"] = requested_origin if requested_origin else allowed_origins[0]
    response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    response.headers['Content-Type'] = 'application/json'
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


@app.on_event("startup")
async def startup():
    """ MongoDB is connected on the bot trainer startup """
    config: dict = Utility.mongoengine_connection(Utility.environment['database']["url"])
    connect(**config)
    await AccountProcessor.default_account_setup()
    AccountProcessor.load_system_properties()


@app.on_event("shutdown")
async def shutdown():
    """ MongoDB is disconnected when bot trainer is shut down """
    disconnect()


@app.get("/", response_model=Response)
def index():
    return {"message": "Event server running!"}


@app.post("/api/events/execute/{event_type}", response_model=Response)
def add_event(
        request: EventRequest,
        is_scheduled: bool = Query(default=False, description="Whether the event is to be run once or scheduled"),
        event_type: EventClass = Path(default=None, description="Event type", example=[e.value for e in EventClass])
):
    request.validate_request(is_scheduled, event_type)
    response, message = EventUtility.add_job(event_type, request.dict(), is_scheduled)
    return {"data": response, "message": message}


@app.put("/api/events/execute/{event_type}", response_model=Response)
def update_scheduled_event(
        request: EventRequest,
        is_scheduled: bool = Query(default=False, description="Whether the event is to be run once or scheduled"),
        event_type: EventClass = Path(default=None, description="Event type", example=[e.value for e in EventClass])
):
    request.validate_request(is_scheduled, event_type)
    response, message = EventUtility.update_job(event_type, request.dict(), is_scheduled)
    return {"data": response, "message": message}


@app.delete("/api/events/{event_id}", response_model=Response)
def delete_scheduled_event(event_id: Text = Path(default=None, description="Event id")):
    return {"data": KScheduler().delete_job(event_id), "message": "Scheduled event deleted!"}
