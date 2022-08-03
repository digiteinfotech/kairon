from typing import Text

from loguru import logger

from kairon import Utility
from kairon.shared.plugins.base import BasePlugin


class IpInfoTracker(BasePlugin):

    def execute(self, ip: Text):
        try:
            if Utility.environment["plugins"]["location"]["enable"]:
                token = Utility.environment["plugins"]["location"]["token"]
                url = f"https://ipinfo.io/{ip}?token={token}"
                tracking_info = Utility.execute_http_request("GET", url)
                return tracking_info
        except Exception as e:
            logger.exception(e)
