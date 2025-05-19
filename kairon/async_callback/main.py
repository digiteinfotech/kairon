import asyncio
from mongoengine import connect, disconnect

from kairon.async_callback.auth import AuthError
from kairon.shared.utils import Utility
from kairon.shared.account.processor import AccountProcessor

Utility.load_environment()

from kairon.async_callback.router import pyscript_callback

from blacksheep import Application, Request, Response
from blacksheep.server.responses import json as JSONResponse
from loguru import logger
from secure import StrictTransportSecurity, ReferrerPolicy, ContentSecurityPolicy, XContentTypeOptions, Server, \
    CacheControl, Secure, PermissionsPolicy
from kairon.api.models import Response


async def startup(app: Application):
    """MongoDB is connected on the bot trainer startup"""
    config: dict = Utility.mongoengine_connection(Utility.environment['database']["url"])
    connect(**config)
    print("Connecting to MongoDB...")
    await asyncio.sleep(1)
    await AccountProcessor.default_account_setup()
    AccountProcessor.load_system_properties()
    print("MongoDB connected.")


async def shutdown(app: Application):
    """Disconnect MongoDB on shutdown"""
    disconnect()
    print("Disconnecting from MongoDB...")
    await asyncio.sleep(1)
    print("MongoDB disconnected.")


app = Application(router=pyscript_callback.router)
app.on_start += startup
app.on_stop += shutdown

hsts = StrictTransportSecurity().include_subdomains().preload().max_age(31536000)
referrer = ReferrerPolicy().no_referrer()
csp = (
    ContentSecurityPolicy().default_src("'self'")
    .frame_ancestors("'self'")
    .form_action("'self'")
    .base_uri("'self'")
    .connect_src("'self' api.spam.com")
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

app.use_cors(
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["content-disposition"],
    allow_credentials=True
)


async def catch_exceptions_middleware(request: Request, handler):
    try:
        response = await handler(request)
        return response

    except AuthError as auth_err:
        return JSONResponse(
            {"success": False,"error_code": 422, "error": str(auth_err)},
            status=422
        )

    except Exception as exc:
        logger.exception(exc)
        error_response = {
            "success": False,
            "error_code": 500,
            "message": str(exc),
        }
        return JSONResponse(error_response, status=500)
hsts_config = {
    "include_subdomains": True,
    "preload": True,
    "max_age": 31536000,
}
referrer_config = {"policy": "no-referrer"}
csp_config = {
    "default-src": ["'self'"],
    "frame-ancestors": ["'self'"],
    "form-action": ["'self'"],
    "base-uri": ["'self'"],
    "connect-src": ["'self'", "api.spam.com"],
    "frame-src": ["'self'"],
    "img-src": ["'self'", "static.spam.com"],
    "script-src": ["'self'"],
    "style-src": ["'self'"]
}
cache_control_config = {"must-revalidate": True}
permissions_config = {
    "geolocation": ["self", "spam.com"],
}


def generate_hsts_header(config):
    directives = [f"max-age={config['max_age']}"]
    if config["include_subdomains"]:
        directives.append("includeSubDomains")
    if config["preload"]:
        directives.append("preload")
    return "; ".join(directives)


def generate_csp_header(config):
    directives = []
    for directive, sources in config.items():
        if sources:
            source_string = " ".join(sources)
            directives.append(f"{directive} {source_string}")
    return "; ".join(directives)


def generate_cache_control_header(config):
    directives = []
    if config["must-revalidate"]:
        directives.append("must-revalidate")
    return ", ".join(directives)


async def add_security_headers_middleware(request, handler):
    response = await handler(request)
    response.headers[b"Strict-Transport-Security"] = generate_hsts_header(hsts_config).encode("utf-8")
    response.headers[b"Referrer-Policy"] = referrer_config["policy"].encode("utf-8")
    response.headers[b"Content-Security-Policy"] = generate_csp_header(csp_config).encode("utf-8")
    response.headers[b"Cache-Control"] = generate_cache_control_header(cache_control_config).encode("utf-8")
    return response

app.middlewares.append(add_security_headers_middleware)
app.middlewares.append(catch_exceptions_middleware)


@app.router.get("/")
async def index():
    return Response(message="Running BlackSheep Async Callback Server")


@app.router.get("/healthcheck")
async def healthcheck():
    return Response(message="Health check OK")
