import ujson as json
from datetime import datetime
from typing import Text, Dict

from loguru import logger
from mongoengine import DoesNotExist, Document

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.chat.broadcast.constants import MessageBroadcastLogType
from kairon.shared.chat.broadcast.data_objects import MessageBroadcastSettings, SchedulerConfiguration, \
    RecipientsConfiguration, TemplateConfiguration, MessageBroadcastLogs
from kairon.shared.chat.data_objects import Channels, ChannelLogs
from kairon.shared.constants import ChannelTypes
from kairon.shared.data.constant import EVENT_STATUS


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
        event_completion_states = [EVENT_STATUS.FAIL.value, EVENT_STATUS.COMPLETED.value]
        is_new_log = log_type in {MessageBroadcastLogType.send.value, MessageBroadcastLogType.self.value} or kwargs.pop("is_new_log", None)
        try:
            if is_new_log:
                raise DoesNotExist()
            log = MessageBroadcastLogs.objects(bot=bot, reference_id=reference_id, log_type=log_type,
                                               status__nin=event_completion_states).get()
        except DoesNotExist:
            log = MessageBroadcastLogs(bot=bot, reference_id=reference_id, log_type=log_type)
        if status:
            log.status = status
        for key, value in kwargs.items():
            if not getattr(log, key, None) and Utility.is_picklable_for_mongo({key: value}):
                setattr(log, key, value)
        log.save()

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
    def get_db_client(bot: Text):
        import pymongo

        config = Utility.get_local_db()
        client = pymongo.MongoClient(
            host=config['host'], username=config.get('username'), password=config.get('password'),
            authSource=config['options'].get("authSource") if config['options'].get("authSource") else "admin"
        )
        db = client.get_database(config['db'])
        coll = db.get_collection(bot)
        return coll

    @staticmethod
    def log_broadcast_in_conversation_history(template_id, contact: Text, template_params, template,
                                              status, mongo_client):
        import time
        from uuid6 import uuid7

        mongo_client.insert_one({
            "type": "broadcast", "sender_id": contact, "conversation_id": uuid7().hex, "timestamp": time.time(),
            "data": {"name": template_id, "template": template, "template_params": template_params}, "status": status
        })

    @staticmethod
    def __add_broadcast_logs_status_and_errors(reference_id: Text, campaign_name: Text, broadcast_logs: Dict[Text, Document]):
        message_ids = list(broadcast_logs.keys())
        channel_logs = ChannelLogs.objects(message_id__in=message_ids, type=ChannelTypes.WHATSAPP.value)
        for log in channel_logs:
            msg_id = log["message_id"]
            broadcast_log = broadcast_logs[msg_id]
            client = MessageBroadcastProcessor.get_db_client(broadcast_log['bot'])
            if log['errors']:
                status = "Failed"
                broadcast_log.update(errors=log['errors'], status="Failed")
            else:
                status = "Success"

            MessageBroadcastProcessor.log_broadcast_in_conversation_history(
                template_id=broadcast_log['template_name'], contact=broadcast_log['recipient'],
                template_params=broadcast_log['template_params'], template=broadcast_log['template'],
                status=status, mongo_client=client
            )

        ChannelLogs.objects(message_id__in=message_ids, type=ChannelTypes.WHATSAPP.value).update(campaign_id=reference_id, campaign_name=campaign_name)

    @staticmethod
    def insert_status_received_on_channel_webhook(reference_id: Text, broadcast_name: Text):
        broadcast_logs = MessageBroadcastProcessor.extract_message_ids_from_broadcast_logs(reference_id)
        if broadcast_logs:
            MessageBroadcastProcessor.__add_broadcast_logs_status_and_errors(reference_id, broadcast_name, broadcast_logs)

    @staticmethod
    def get_channel_metrics(channel_type: Text, bot: Text):
        result = list(ChannelLogs.objects.aggregate([
            {'$match': {'bot': bot, 'type': channel_type}},
            {'$group': {'_id': {'campaign_id': '$campaign_id', 'status': '$status'}, 'count': {'$sum': 1}}},
            {'$group': {'_id': '$_id.campaign_id', 'status': {'$push': {'k': '$_id.status', 'v': '$count'}}}},
            {'$project': {'campaign_id': '$_id', 'status': {'$arrayToObject': '$status'}, '_id': 0}}
        ]))
        return result

    @staticmethod
    def get_campaign_id(message_id: Text):
        campaign_id = None
        try:
            log = MessageBroadcastLogs.objects(api_response__messages__id=message_id, log_type=MessageBroadcastLogType.send.value)
            if log:
                campaign_id = log[0].reference_id
        except Exception as e:
            logger.debug(e)

        return campaign_id
