import json
from datetime import datetime
from typing import Text, Dict

from loguru import logger
from bson import ObjectId
from mongoengine import DoesNotExist
from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.chat.data_objects import Channels
from kairon.shared.chat.notifications.constants import MessageBroadcastLogType
from kairon.shared.chat.notifications.data_objects import MessageBroadcastSettings, SchedulerConfiguration, \
    DataExtractionConfiguration, RecipientsConfiguration, TemplateConfiguration, MessageBroadcastLogs


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
        return MessageBroadcastSettings(**config).save().to_mongo().to_dict()["_id"].__str__()

    @staticmethod
    def update_scheduled_task(notification_id: Text, bot: Text, user: Text, config: Dict):
        if not config.get("scheduler_config"):
            raise AppException("scheduler_config is required!")
        try:
            settings = MessageBroadcastSettings.objects(id=notification_id, bot=bot, status=True).get()
            settings.channel_id = config["connector_type"]
            settings.scheduler_config = SchedulerConfiguration(**config["scheduler_config"])
            settings.data_extraction_config = DataExtractionConfiguration(**config["data_extraction_config"]) \
                if config.get("data_extraction_config") else None
            settings.recipients_config = RecipientsConfiguration(**config["recipients_config"])
            settings.template_config = [TemplateConfiguration(**template) for template in config["template_config"]]
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
            if log_type == MessageBroadcastLogType.send.value:
                raise DoesNotExist()
            log = MessageBroadcastLogs.objects(bot=bot, reference_id=reference_id, log_type=log_type).get()
        except DoesNotExist:
            if not reference_id:
                reference_id = ObjectId().__str__()
            log = MessageBroadcastLogs(bot=bot, reference_id=reference_id, log_type=log_type)
        if status:
            log.status = status
        for key, value in kwargs.items():
            if not getattr(log, key, None):
                setattr(log, key, value)
        log.save()
        return reference_id

    @staticmethod
    def get_broadcast_logs(bot: Text, start_idx: int = 0, page_size: int = 10, **kwargs):
        kwargs["bot"] = bot
        query_objects = MessageBroadcastLogs.objects(**kwargs)
        total_count = MessageBroadcastLogs.objects(**kwargs).count()
        logs = query_objects.skip(start_idx).limit(page_size).exclude('id').to_json()
        logs = json.loads(logs)
        return logs, total_count
