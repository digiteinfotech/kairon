import json
from typing import Text

from loguru import logger
from mongoengine import DoesNotExist

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.data.audit.data_objects import AuditLogData
from kairon.shared.data.constant import AuditlogActions
from kairon.shared.data.data_objects import EventConfig


class AuditDataProcessor:

    @staticmethod
    def log(entity, account: int = None, bot: Text = None, email: Text = None, data: dict = None, **kwargs):
        """
        Logs information into auditlog

        :param entity: Type of UserActivity
        :param account: account id
        :param bot: bot id
        :param email: email
        :param data: dictionary containing data
        """

        from kairon.shared.account.processor import AccountProcessor

        action = kwargs.get("action")
        attribute = AuditDataProcessor.get_attributes({"bot": bot, "account": account, "email": email})
        user = email if email else AccountProcessor.get_account(account)['user']
        audit_log = AuditLogData(attributes=attribute,
                                 user=user,
                                 action=action,
                                 entity=entity,
                                 data=data)
        audit_log.save()
        AuditDataProcessor.publish_auditlog(auditlog=audit_log, event_url=kwargs.get("event_url"))

    @staticmethod
    def save_and_publish_auditlog(document, name, **kwargs):
        """
        Takes document through signals to save and publish into auditlog

        :param document: document to be saved and published
        :param name: name of the document
        """

        action = kwargs.get("action")

        if action == AuditlogActions.BULK_INSERT.value:
            AuditDataProcessor.log_bulk_insert(document, name)
            return

        if hasattr(document, 'status') and not document.status:
            action = AuditlogActions.SOFT_DELETE.value

        attribute = AuditDataProcessor.get_attributes(document)
        user = kwargs.get("user") or document.user

        audit_log = AuditLogData(attributes=attribute,
                                 user=user,
                                 action=action,
                                 entity=name,
                                 data=document.to_mongo().to_dict())
        audit_log.save()
        AuditDataProcessor.publish_auditlog(auditlog=audit_log, event_url=kwargs.get("event_url"))

    @staticmethod
    def log_bulk_insert(documents, name):
        action = AuditlogActions.BULK_INSERT.value
        inserted_docs = []
        for doc in documents:
            attribute = AuditDataProcessor.get_attributes(doc)
            inserted_docs.append(
                AuditLogData(attributes=attribute, user=doc.user, action=action, entity=name, data=doc.to_mongo().to_dict())
            )
        AuditLogData.objects.insert(inserted_docs)

    @staticmethod
    def get_attributes(document):
        """
        Fetches ids of document

        :param document: document
        return: dictionary containing document ids
        """

        attributes_list = []
        attributes = Utility.environment['events']['audit_logs']['attributes']
        for attr in attributes:
            if isinstance(document, dict) and document.get(attr):
                attributes_list.append({'key': attr, 'value': document[attr]})
            elif hasattr(document, attr):
                attributes_list.append({'key': attr, 'value': getattr(document, attr)})

        if not attributes_list:
            if not isinstance(document, dict):
                key = f"{document._class_name.__str__()}_id"
                attributes_list.append({'key': key, 'value': document.id.__str__()})
            else:
                attributes_list.append({'key': 'email', 'value': document['email']})

        return attributes_list

    @staticmethod
    def publish_auditlog(auditlog, **kwargs):
        """
        Publishes auditlog

        :param auditlog: auditlog
        :returns if bot event is not present
        """

        try:
            bot_value = next((item for item in auditlog.attributes if item['key'] == 'bot' and item['value'] is not None), None)
            if not bot_value:
                logger.debug("Only bot events can be emitted!")
                return
            event_config = EventConfig.objects(bot=bot_value['value']).get()

            headers = json.loads(Utility.decrypt_message(event_config.headers))
            ws_url = event_config.ws_url
            method = event_config.method
            if ws_url:
                Utility.execute_http_request(request_method=method, http_url=ws_url,
                                             request_body=auditlog.to_mongo().to_dict(), headers=headers, timeout=5)
        except (DoesNotExist, AppException):
            return
