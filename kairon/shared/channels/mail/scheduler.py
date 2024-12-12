from urllib.parse import urljoin
from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.channels.mail.processor import MailProcessor
from kairon.shared.chat.data_objects import Channels
from kairon.shared.constants import ChannelTypes


class MailScheduler:

    @staticmethod
    def request_epoch(bot: str):
        if not MailProcessor.validate_smtp_connection(bot):
            raise AppException("Failed to validate smtp connection, please revise mail channel configuration")

        if not MailProcessor.validate_imap_connection(bot):
            raise AppException("Failed to validate imap connection, please revise mail channel configuration")

        event_server_url = Utility.get_event_server_url()
        resp = Utility.execute_http_request(
            "GET",
            urljoin(
                event_server_url,
                f"/api/mail/schedule/{bot}",
            ),
            err_msg="Failed to request epoch",
        )
        if not resp['success']:
            raise AppException("Failed to request email channel epoch")

    @staticmethod
    def request_stop(bot: str):
        event_server_url = Utility.get_event_server_url()
        if Utility.is_exist(Channels, raise_error=False, bot=bot, connector_type=ChannelTypes.MAIL.value):
            resp = Utility.execute_http_request(
                "GET",
                urljoin(
                    event_server_url,
                    f"/api/mail/stop/{bot}",
                ),
                err_msg="Failed to request epoch",
            )
            if not resp['success']:
                raise AppException("Failed to stop email channel reading")
        else:
            raise AppException("Mail channel does not exist")









