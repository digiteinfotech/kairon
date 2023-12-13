import json
from datetime import datetime
from typing import Text, Dict

from bson import ObjectId
from loguru import logger
from mongoengine import DoesNotExist, Document

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.chat.broadcast.constants import MessageBroadcastLogType
from kairon.shared.chat.broadcast.data_objects import MessageBroadcastSettings, SchedulerConfiguration, \
    RecipientsConfiguration, TemplateConfiguration, MessageBroadcastLogs
from kairon.shared.chat.data_objects import Channels, ChannelLogs


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
        broadcast_logs = {
            message['id']: log
            for log in message_broadcast_logs
            if log.api_response and log.api_response.get('messages', [])
            for message in log.api_response['messages']
            if message['id']
        }
        return broadcast_logs

    @staticmethod
    def __add_broadcast_logs_status_and_errors(reference_id: Text, broadcast_logs: Dict[Text, Document]):
        message_ids = list(broadcast_logs.keys())
        channel_logs = ChannelLogs.objects(message_id__in=message_ids)
        for log in channel_logs:
            if log['errors']:
                msg_id = log["message_id"]
                broadcast_logs[msg_id].update(errors=log['errors'], status="Failed")
            log.update(campaign_id=reference_id)

    @staticmethod
    def insert_status_received_on_channel_webhook(reference_id: Text):
        broadcast_logs = MessageBroadcastProcessor.extract_message_ids_from_broadcast_logs(reference_id)
        if broadcast_logs:
            MessageBroadcastProcessor.__add_broadcast_logs_status_and_errors(reference_id, broadcast_logs)
