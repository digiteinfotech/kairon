from urllib.parse import urljoin


from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.channels.mail.processor import MailProcessor


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









