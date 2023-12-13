import json
from datetime import datetime
from typing import Text, Dict, List

from bson import ObjectId
from loguru import logger
from mongoengine import DoesNotExist, Document

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.chat.broadcast.constants import MessageBroadcastLogType
from kairon.shared.chat.broadcast.data_objects import MessageBroadcastSettings, SchedulerConfiguration, \
    RecipientsConfiguration, TemplateConfiguration, MessageBroadcastLogs
from kairon.shared.chat.data_objects import Channels, WhatsappAuditLog


class MessageBroadcastProcessor:

    @staticmethod
    def get_settings(notification_id: Text, bot: Text):
        try:
            settings = MessageBroadcastSettings.objects(id=notification_id, bot=bot, status=True).get()
            settings = settings.to_mongo().to_dict()
            settings["_id"] = settings["_id"].__str__()
            return settings
        except DoesNotExist:
            raise AppException("Notification settings not found!")

    @staticmethod
    def list_settings(bot: Text, **kwargs):
        kwargs['bot'] = bot
        for settings in MessageBroadcastSettings.objects(**kwargs):
            settings = settings.to_mongo().to_dict()
            settings['_id'] = settings['_id'].__str__()
            yield settings

    @staticmethod
    def add_scheduled_task(bot: Text, user: Text, config: Dict):
        channel = config.get("connector_type")
        Utility.is_exist(MessageBroadcastSettings, f"Schedule with name '{config['name']}' exists!", bot=bot,
                         name=config['name'], status=True)
        if not Utility.is_exist(Channels, raise_error=False, bot=bot, connector_type=channel):
            raise AppException(f"Channel '{channel}' not configured!")
        config["bot"] = bot
        config["user"] = user
        return MessageBroadcastSettings(**config).save().id.__str__()

    @staticmethod
    def update_scheduled_task(notification_id: Text, bot: Text, user: Text, config: Dict):
        if not config.get("scheduler_config"):
            raise AppException("scheduler_config is required!")
        try:
            settings = MessageBroadcastSettings.objects(id=notification_id, bot=bot, status=True).get()
            settings.name = config["name"]
            settings.connector_type = config["connector_type"]
            settings.broadcast_type = config["broadcast_type"]
            settings.scheduler_config = SchedulerConfiguration(**config["scheduler_config"])
            settings.recipients_config = RecipientsConfiguration(**config["recipients_config"]) if config.get("recipients_config") else None
            settings.template_config = [TemplateConfiguration(**template) for template in config.get("template_config") or []]
            settings.pyscript = config.get("pyscript")
            settings.user = user
            settings.timestamp = datetime.utcnow()
            settings.save()
        except DoesNotExist as e:
            logger.exception(e)
            raise AppException("Notification settings not found!")

    @staticmethod
    def delete_task(notification_id: Text, bot: Text, delete_permanently: bool = True):
        try:
            if delete_permanently:
                settings = MessageBroadcastSettings.objects(id=notification_id, bot=bot).get()
                settings.delete()
            else:
                settings = MessageBroadcastSettings.objects(id=notification_id, bot=bot).get()
                settings.status = False
                settings.save()
        except DoesNotExist:
            raise AppException("Notification settings not found!")

    @staticmethod
    def add_event_log(bot: Text, log_type: Text, reference_id: Text = None, status: Text = None, **kwargs):
        try:
            if log_type in {MessageBroadcastLogType.send.value, MessageBroadcastLogType.self.value}:
                raise DoesNotExist()
            log = MessageBroadcastLogs.objects(bot=bot, reference_id=reference_id, log_type=log_type).get()
        except DoesNotExist:
            if not reference_id:
                reference_id = ObjectId().__str__()
            log = MessageBroadcastLogs(bot=bot, reference_id=reference_id, log_type=log_type)
        if status:
            log.status = status
        for key, value in kwargs.items():
            if not getattr(log, key, None) and Utility.is_picklable_for_mongo({key: value}):
                setattr(log, key, value)
        log.save()
        return reference_id

    @staticmethod
    def get_broadcast_logs(bot: Text, start_idx: int = 0, page_size: int = 10, **kwargs):
        kwargs["bot"] = bot
        start_idx = int(start_idx)
        page_size = int(page_size)
        query_objects = MessageBroadcastLogs.objects(**kwargs).order_by("-timestamp")
        total_count = MessageBroadcastLogs.objects(**kwargs).count()
        logs = query_objects.skip(start_idx).limit(page_size).exclude('id').to_json()
        logs = json.loads(logs)
        return logs, total_count

    @staticmethod
    def extract_message_ids_from_broadcast_logs(reference_id: Text):
        message_broadcast_logs = MessageBroadcastLogs.objects(reference_id=reference_id,
                                                              log_type=MessageBroadcastLogType.send.value)
        message_ids = [
            message['id']
            for document in message_broadcast_logs
            if document.api_response and document.api_response.get('messages', [])
            for message in document.api_response['messages']
            if message['id']
        ]
        return message_broadcast_logs, message_ids

    @staticmethod
    def update_message_broadcast_logs(reference_id: Text):
        message_broadcast_logs, message_ids = MessageBroadcastProcessor.extract_message_ids_from_broadcast_logs(
            reference_id)
        if message_ids:
            MessageBroadcastProcessor.add_broadcast_logs_status_and_errors(message_ids, message_broadcast_logs)

    @staticmethod
    def add_broadcast_logs_status_and_errors(message_ids: List, message_broadcast_logs: List[Document]):
        whatsapp_audit_logs = WhatsappAuditLog.objects(status='sent', message_id__in=message_ids)
        for audit_log in whatsapp_audit_logs:
            if audit_log['errors']:
                matching_message_broadcast_log = next(
                    (doc for doc in message_broadcast_logs if any(
                        msg['id'] == audit_log['message_id'] for msg in doc.api_response.get('messages', [])
                    )),
                    None
                )
                if matching_message_broadcast_log:
                    matching_message_broadcast_log.update(
                        errors=audit_log['errors'],
                        status='FAILURE'
                    )
