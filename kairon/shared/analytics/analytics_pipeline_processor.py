from datetime import datetime
from typing import Text, Dict
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from loguru import logger
from mongoengine import DoesNotExist

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import AnalyticsPipelineConfig, SchedulerConfiguration, EmailActionConfig
from kairon.shared.callback.data_objects import CallbackConfig
from kairon.shared.chat.broadcast.data_objects import AnalyticsPipelineLogs

class AnalyticsPipelineProcessor:

    @staticmethod
    def add_scheduled_task(bot, user, config):
        """Store event config."""

        Utility.is_exist(AnalyticsPipelineConfig, f"Schedule with name '{config['pipeline_name']}' exists!", bot=bot,
                         pipeline_name=config['pipeline_name'], status=True)
        config["bot"] = bot
        config["user"] = user
        return AnalyticsPipelineConfig(**config).save().id.__str__()

    @staticmethod
    def delete_task(notification_id: Text, bot: Text, delete_permanently: bool = True):
        try:
            if delete_permanently:
                settings = AnalyticsPipelineConfig.objects(id=notification_id, bot=bot).get()
                settings.delete()
            else:
                settings = AnalyticsPipelineConfig.objects(id=notification_id, bot=bot).get()
                settings.status = False
                settings.save()
        except DoesNotExist:
            raise AppException("Notification settings not found!")

    @staticmethod
    def retrieve_config(event_id, bot):
        try:
            settings = AnalyticsPipelineConfig.objects(id=event_id, bot=bot).get()
            settings = settings.to_mongo().to_dict()
            settings["_id"] = settings["_id"].__str__()
            return settings
        except DoesNotExist:
            raise AppException("Notification settings not found!")


    @staticmethod
    def get_all_analytics_pipelines(bot: str):
        """
        Fetch all analytics pipeline events for a bot with proper formatting.
        All heavy lifting stays inside business logic.
        """
        events = AnalyticsPipelineConfig.objects(bot=bot)

        formatted = []
        for event in events:
            doc = event.to_mongo().to_dict()
            doc["_id"] = str(doc["_id"])
            formatted.append(doc)

        return formatted


    @staticmethod
    def delete_analytics_pipeline(bot: str, pipeline_id: str):
        pipeline = AnalyticsPipelineConfig.objects(bot=bot, id=pipeline_id).first()
        if not pipeline:
            raise HTTPException(404, "Pipeline config not found for this bot")

        pipeline.delete()
        return True


    @staticmethod
    def update_scheduled_task(event_id: str, bot: str, user: str, config: Dict):
        """
        Update a scheduled analytics pipeline event.
        """
        if not config.get("scheduler_config"):
            raise AppException("scheduler_config is required!")

        try:
            settings = AnalyticsPipelineConfig.objects(id=event_id, bot=bot, status=True).get()

            settings.pipeline_name = config["pipeline_name"]
            settings.callback_name = config.get("callback_name")

            scheduler_config = SchedulerConfiguration(**config["scheduler_config"])

            if scheduler_config.expression_type == "epoch":
                try:
                    epoch_time = int(scheduler_config.schedule)
                except ValueError:
                    raise AppException("schedule must be a valid integer epoch timestamp")

                tzinfo = ZoneInfo(scheduler_config.timezone or "UTC")
                run_at = datetime.fromtimestamp(epoch_time, tzinfo)
                scheduler_config.schedule = run_at.isoformat()

            settings.scheduler_config = scheduler_config

            settings.timestamp = datetime.utcnow()
            settings.user = user
            settings.data_deletion_policy = config.get("data_deletion_policy") or []
            settings.triggers = config.get("triggers") or []

            settings.save()

        except DoesNotExist:
            raise AppException("Analytics pipeline event not found!")
        except Exception as e:
            logger.exception(e)
            raise AppException(str(e))

    @staticmethod
    def get_pipeline_code(bot: str, callback_name: str):
        """
        Retrieve pyscript code for an analytics pipeline using the action_name sent in the event.
        """
        callback_config = CallbackConfig.objects(
            bot=bot,
            name=callback_name
        ).first()

        if not callback_config:
            raise AppException(f"No callback config found for callback: {callback_name}")

        return callback_config.pyscript_code

    @staticmethod
    def add_event_log(event_id, bot, user, status, exception, pipeline_name, callback_name, start_time, end_time):
        AnalyticsPipelineLogs(
            event_id=event_id,
            bot = bot,
            user = user,
            status=status,
            pipeline_name=pipeline_name,
            callback_name=callback_name,
            exception=exception,
            start_timestamp=start_time,
            end_timestamp=end_time,
        ).save()

    @staticmethod
    def trigger_email(config: dict, bot: str):
        from kairon.shared.pyscript.callback_pyscript_utils import CallbackScriptUtility
        triggers = config.get("triggers")

        action_name = triggers[0].get("action_name")
        if not action_name:
            logger.warning("No action_name in trigger configuration")
            return

        email_action = EmailActionConfig.objects(bot=bot, action_name=action_name).first()
        CallbackScriptUtility.send_email(
            email_action.action_name,
            from_email=email_action.from_email.value,
            to_email=email_action.to_email.value[0],
            subject=email_action.subject,
            body=email_action.response,
            bot=email_action.bot
        )
