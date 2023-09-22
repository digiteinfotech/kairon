import json

from loguru import logger

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.data.audit.data_objects import AuditLogData
from kairon.shared.data.constant import AuditlogActions


class AuditProcessor:

    @staticmethod
    def save_auditlog_document(audit, user, entity, data, **kwargs):
        try:
            action = kwargs.get("action")
        except AttributeError:
            action = kwargs.get("action")
        audit_log = AuditLogData(metadata=audit,
                                 user=user,
                                 action=action,
                                 entity=entity,
                                 data=data)
        audit_log.save()
        AuditProcessor.publish_auditlog(auditlog=audit_log, event_url=kwargs.get("event_url"))

    @staticmethod
    def save_and_publish_auditlog(document, name, **kwargs):
        try:
            action = kwargs.get("action")
            if not document.status:
                action = AuditlogActions.SOFT_DELETE.value
        except AttributeError:
            action = kwargs.get("action")

        audit = [{"key": "bot", "value": AuditProcessor.get_auditlog_id_and_mapping(document)}]

        audit_log = AuditLogData(metadata=audit,
                                 user=document.user,
                                 action=action,
                                 entity=name,
                                 data=document.to_mongo().to_dict())
        audit_log.save()
        AuditProcessor.publish_auditlog(auditlog=audit_log, event_url=kwargs.get("event_url"))

    @staticmethod
    def get_auditlog_id_and_mapping(document):
        try:
            auditlog_id = document.bot.__str__()
        except AttributeError:
            auditlog_id = document.id.__str__()

        return auditlog_id

    @staticmethod
    def publish_auditlog(auditlog, **kwargs):
        from kairon.shared.data.data_objects import EventConfig
        from mongoengine.errors import DoesNotExist

        try:
            for data in auditlog.metadata:
                if data.key != 'bot' and data.value is None:
                    logger.debug("Only bot level event config is supported as of")
                    return
                event_config = EventConfig.objects(bot=data.value).get()

                headers = json.loads(Utility.decrypt_message(event_config.headers))
                ws_url = event_config.ws_url
                method = event_config.method
                if ws_url:
                    Utility.execute_http_request(request_method=method, http_url=ws_url,
                                                 request_body=auditlog.to_mongo().to_dict(), headers=headers, timeout=5)
        except (DoesNotExist, AppException):
            return
