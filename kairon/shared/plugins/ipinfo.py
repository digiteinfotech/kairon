from loguru import logger

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.plugins.base import BasePlugin


class IpInfoTracker(BasePlugin):

    def execute(self, **kwargs):
        if Utility.environment["plugins"]["location"]["enable"]:
            ip = kwargs.get("ip")
            if Utility.check_empty_string(ip):
                raise AppException("ip is required")
            try:
                token = Utility.environment["plugins"]["location"]["token"]
                url = f"https://ipinfo.io/{ip}?token={token}"
                tracking_info = Utility.execute_http_request("GET", url)
                return tracking_info
            except Exception as e:
                logger.exception(e)
