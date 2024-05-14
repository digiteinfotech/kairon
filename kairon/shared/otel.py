from kairon.shared.utils import Utility
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from functools import wraps
from opentelemetry.trace import get_tracer, SpanKind
from loguru import logger


def instrument_fastapi(app: FastAPI):
    enable = Utility.environment.get('apm', {}).get('enable')
    if enable:
        FastAPIInstrumentor.instrument(app)


def instrument(func):
    @wraps(func)
    def wrapper_func(*args, **kwargs):
        enable = Utility.environment.get('apm', {}).get('enable')
        if enable:
            tracer = get_tracer(__name__)
            with tracer.start_as_current_span(__name__, kind=SpanKind.SERVER):
                logger.info(f'Started a {__name__} span')
                with tracer.start_span("Child Span"):
                    return func(*args, **kwargs)
        else:
            return func(*args, **kwargs)

    return wrapper_func


def record_custom_attributes(**kwargs):
    if Utility.environment.get("apm", {}).get("enable"):
        tracer = get_tracer(__name__)
        logger.info(f"tracer started {__name__}")
        with tracer.start_as_current_span("Root Span", kind=SpanKind.SERVER) as current_span:
            logger.info(f"tracer data: {kwargs}")
            logger.info(f"span : {current_span}")
            for key, value in kwargs.items():
                current_span.set_attribute(key, value)
