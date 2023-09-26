import json
from datetime import datetime

from fastapi import HTTPException
from loguru import logger
from starlette import status

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.constants import UserActivityType
from kairon.shared.data.audit.data_objects import AuditLogData
from kairon.shared.data.constant import AuditlogActions


class AuditProcessor:

    @staticmethod
    def save_auditlog_document(bot, account, email, entity, data, **kwargs):
        action = kwargs.get("action")
        attribute = [{'key': 'bot', 'value': bot}, {'key': 'account', 'value': account}]
        user = email if email else AccountProcessor.get_account(account)['user']
        audit_log = AuditLogData(attributes=attribute,
                                 user=user,
                                 action=action,
                                 entity=entity,
                                 data=data)
        audit_log.save()
        AuditProcessor.publish_auditlog(auditlog=audit_log, event_url=kwargs.get("event_url"))

    @staticmethod
    def save_and_publish_auditlog(document, name, **kwargs):
        action = kwargs.get("action")
        if hasattr(document, 'status') and not document.status:
            action = AuditlogActions.SOFT_DELETE.value

        attribute = AuditProcessor.get_attributes(document)

        audit_log = AuditLogData(attributes=attribute,
                                 user=document.user,
                                 action=action,
                                 entity=name,
                                 data=document.to_mongo().to_dict())
        audit_log.save()
        AuditProcessor.publish_auditlog(auditlog=audit_log, event_url=kwargs.get("event_url"))

    @staticmethod
    def get_attributes(document):
        attributes_list = []
        auditlog_id = None
        attributes = Utility.environment['events']['audit_logs']['attributes']
        if hasattr(document, 'account') and hasattr(document, 'bot'):
            for value in attributes:
                attibute_info = {}
                mapping = value
                if value == 'account':
                    auditlog_id = document.account.__str__()
                elif value == 'bot':
                    auditlog_id = document.bot.__str__()
                attibute_info['key'] = mapping
                attibute_info['value'] = auditlog_id
                attributes_list.append(attibute_info)
        else:
            if hasattr(document, 'account'):
                mapping = 'account'
                auditlog_id = document.account.__str__()
                attibute_info = {'key': mapping, 'value': auditlog_id}
                attributes_list.append(attibute_info)
            elif hasattr(document, 'bot'):
                mapping = 'bot'
                auditlog_id = document.bot.__str__()
                attibute_info = {'key': mapping, 'value': auditlog_id}
                attributes_list.append(attibute_info)
            else:
                mapping = f"{document._class_name.__str__()}_id"
                auditlog_id = document.id.__str__()
                attibute_info = {'key': mapping, 'value': auditlog_id}
                attributes_list.append(attibute_info)

        return attributes_list

    @staticmethod
    def publish_auditlog(auditlog, **kwargs):
        from kairon.shared.data.data_objects import EventConfig
        from mongoengine.errors import DoesNotExist

        try:
            bot_value = next((item for item in auditlog.attributes if item['key'] == 'bot' and item['value'] is not None), None)
            if not bot_value:
                logger.debug("Only bot level event config is supported as of")
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

    @staticmethod
    def is_relogin_done(uuid_value, email):
        if uuid_value is not None and Utility.is_exist(
                AuditLogData, raise_error=False, user=email, action=AuditlogActions.ACTIVITY.value,
                entity=UserActivityType.link_usage.value,
                data__status="done", data__uuid=uuid_value, check_base_fields=False
        ):
            raise AppException("Password already reset!")

    @staticmethod
    def is_password_used_before(email, password):
        user_act_log = AuditLogData.objects(user=email, action=AuditlogActions.ACTIVITY.value,
                                            entity=UserActivityType.reset_password.value).order_by('-timestamp')
        if any(act_log.data is not None and act_log.data.get("password") is not None and
               Utility.verify_password(password.strip(), act_log.data.get("password"))
               for act_log in user_act_log):
            raise AppException("You have already used that password, try another")

    @staticmethod
    def update_reset_password_link_usage(uuid_value, email):
        if uuid_value is not None:
            AuditLogData.objects(user=email, action=AuditlogActions.ACTIVITY.value,
                                 entity=UserActivityType.link_usage.value,
                                 data__status="pending", data__uuid=uuid_value).order_by('-timestamp') \
                .update_one(set__data__status="done")

    @staticmethod
    def is_password_reset(payload, username):
        iat_val = payload.get("iat")
        if iat_val is not None:
            issued_at = datetime.utcfromtimestamp(iat_val)
            if Utility.is_exist(
                    AuditLogData, raise_error=False, user=username, action=AuditlogActions.ACTIVITY.value,
                    entity=UserActivityType.reset_password.value,
                    timestamp__gte=issued_at, check_base_fields=False):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail='Session expired. Please login again.',
                )
