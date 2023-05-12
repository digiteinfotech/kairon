import logging
from typing import Text

from kairon import Utility
from kairon.shared.plugins.base import BasePlugin

logger = logging.getLogger(__name__)


class IpInfoTracker(BasePlugin):

    def execute(self, ip: Text, **kwargs):
        if Utility.environment["plugins"]["location"]["enable"]:
            if Utility.check_empty_string(ip):
                logger.error("ip is required")
                return
            try:
                headers = {"user-agent": "IPinfoClient/Python3.8/4.2.1", "accept": "application/json"}
                token = Utility.environment["plugins"]["location"]["token"]
                url = f"https://ipinfo.io/{ip}?token={token}"
                tracking_info = Utility.execute_http_request("GET", url, headers=headers)
                return tracking_info
            except Exception as e:
                logger.exception(e)
