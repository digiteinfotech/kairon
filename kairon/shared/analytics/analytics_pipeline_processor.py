from datetime import datetime
from typing import Text, Dict
from zoneinfo import ZoneInfo

from bson import ObjectId
from fastapi import HTTPException
from loguru import logger
from mongoengine import DoesNotExist

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import AnalyticsPipelineConfig
from kairon.shared.callback.data_objects import CallbackData, CallbackConfig
from kairon.shared.data.data_models import AnalyticsSchedulerConfig
from kairon.shared.data.processor import MongoProcessor


class AnalyticsPipelineProcessor:

    @staticmethod
    def add_scheduled_task(bot, user, config):
        """Store event config."""
        Utility.is_exist(AnalyticsPipelineConfig, f"Schedule with name '{config['name']}' exists!", bot=bot,
                         name=config['name'], status=True)
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
    def add_event_log(bot, event_id, reference_id, status, exception, config):
        MongoProcessor.add_analytics_event_log(
            bot=bot,
            event_id=event_id,
            status=status,
            exception=exception,
            reference_id=reference_id,
            config=config,
            timestamp=datetime.utcnow()
        )

    @staticmethod
    def execute_pipeline(bot, user, pipeline_name, callback_name, config):
        """
        Here you call your actual pipeline logic.
        Example: call lambda, invoke internal function, etc.
        """
        print(f"Running pipeline {pipeline_name} via callback {callback_name}")


    @staticmethod
    def get_analytics_pipeline(bot: str, pipeline_name: str):
        pipeline = AnalyticsPipelineConfig.objects(bot=bot, pipeline_name=pipeline_name).first()
        if not pipeline:
            raise HTTPException(404, "Pipeline config not found for this bot")
        return pipeline

    @staticmethod
    def get_all_analytics_pipelines(bot: str):
        return list(AnalyticsPipelineConfig.objects(bot=bot))


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
            settings = AnalyticsPipelineConfig.objects(
                id=event_id, bot=bot, status=True
            ).get()

            settings.pipeline_name = config["pipeline_name"]
            settings.callback_name = config.get("callback_name")
            settings.pipeline_params = config.get("pipeline_params") or {}

            scheduler_config = AnalyticsSchedulerConfig(**config["scheduler_config"])

            if scheduler_config.expression_type == "epoch":
                try:
                    epoch_time = int(scheduler_config.schedule)
                except ValueError:
                    raise AppException("schedule must be a valid integer epoch timestamp")

                tzinfo = ZoneInfo(scheduler_config.timezone or "UTC")
                run_at = datetime.fromtimestamp(epoch_time, tzinfo)
                scheduler_config.schedule = run_at

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

        # callback_data = CallbackData.objects(
        #     bot=bot,
        #     action_name=action_name
        # ).first()
        #
        # if not callback_data:
        #     raise AppException(f"No callback data found for action: {action_name}")
        #
        # callback_name = callback_data.callback_name

        callback_config = CallbackConfig.objects(
            bot=bot,
            name=callback_name
        ).first()

        if not callback_config:
            raise AppException(f"No callback config found for callback: {callback_name}")

        return callback_config.pyscript_code
