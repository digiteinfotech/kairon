from loguru import logger

from kairon.shared.utils import Utility

MIN_ALLOWED_OVERRIDE = 60   # a misconfigured 0/1 must never open up per-second pipelines


def analytics_min_trigger_interval() -> int:
    """
    Minimum seconds between runs of a scheduled Analytics Pipeline.
    `events.scheduler.analytics_min_trigger_interval` (env ANALYTICS_MIN_TRIGGER_INTERVAL) overrides it for analytics
    pipelines only. Unset (the default) keeps the platform-wide `min_trigger_interval`, so nothing changes until a
    deployment opts in; message broadcasts are never affected.
    """
    scheduler = Utility.environment["events"]["scheduler"]
    default = int(scheduler["min_trigger_interval"])
    override = scheduler.get("analytics_min_trigger_interval")
    if override in (None, ""):
        return default
    try:
        value = int(override)
    except (TypeError, ValueError):
        value = None
    if value is None or value < MIN_ALLOWED_OVERRIDE:
        # Fail safe: an unusable override keeps the strict platform limit instead of loosening or breaking validation.
        logger.warning("Ignoring invalid ANALYTICS_MIN_TRIGGER_INTERVAL (must be an integer >= %s)" % MIN_ALLOWED_OVERRIDE)
        return default
    return value
