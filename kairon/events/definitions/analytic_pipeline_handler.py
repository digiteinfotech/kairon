from datetime import datetime
from typing import Text, Dict
from zoneinfo import ZoneInfo

from loguru import logger

from kairon.events.definitions.scheduled_base import ScheduledEventsBase
from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import AnalyticsPipelineConfig
from kairon.shared.analytics.analytics_pipeline_processor import AnalyticsPipelineProcessor
from kairon.shared.concurrency.actors.analytics_runner import AnalyticsRunner
from kairon.shared.concurrency.orchestrator import ActorOrchestrator
from kairon.shared.constants import EventClass, ActorType
from kairon.shared.utils import Utility
from kairon.shared.data.constant import EVENT_STATUS


class AnalyticsPipelineEvent(ScheduledEventsBase):
    """
    Event handler for analytics pipeline execution.
    """

    def __init__(self, bot: Text, user: Text):
        super().__init__()
        self.bot = bot
        self.user = user

    def validate(self, pipeline_name: Text):
        """Check if pipeline exists and is active."""
        pipeline = AnalyticsPipelineProcessor.get_analytics_pipeline(self.bot, pipeline_name)
        if not pipeline or not pipeline.status:
            raise AppException("Pipeline not found or inactive!")

    def execute(self, event_id: Text, **kwargs):
        """
        Worker executes this method when event server triggers it.
        """
        config = None
        reference_id = None
        status = EVENT_STATUS.INITIATED.value
        exception = None

        try:
            config = AnalyticsPipelineProcessor.retrieve_config(event_id, self.bot)

            pipeline_name = config["pipeline_name"]
            callback_name = config["callback_name"]

            logger.info(f"Executing analytics pipeline: {pipeline_name}")

            source_code = AnalyticsPipelineProcessor.get_pipeline_code(
                bot=self.bot,
                callback_name=callback_name
            )

            predefined_objects = {
                "config": config,
                "bot": self.bot,
                "user": self.user,
                "pipeline_name": pipeline_name,
                "callback_name": callback_name,
                "event_id": event_id,
                "slot": {"bot": self.bot},
            }

            runner = AnalyticsRunner()
            output = runner.execute(source_code, predefined_objects=predefined_objects)
            status = EVENT_STATUS.COMPLETED.value

        except Exception as e:
            logger.exception(e)
            status = EVENT_STATUS.FAIL.value
            exception = str(e)

        finally:
            AnalyticsPipelineProcessor.add_event_log(
                bot=self.bot,
                event_id=event_id,
                reference_id=reference_id,
                status=status,
                exception=exception,
                config=config
            )
            if config and config.get("scheduler_config", {}).get("expression_type") != "cron":
                AnalyticsPipelineProcessor.delete_task(event_id, self.bot)


    def _add_schedule(self, config: Dict):
        """Add cron schedule."""
        event_id = None

        if not config.get("scheduler_config") or not config["scheduler_config"].get("schedule"):
            raise AppException("scheduler_config is required!")
        try:
            event_id = AnalyticsPipelineProcessor.add_scheduled_task(self.bot, self.user, config)
            cron_exp = config["scheduler_config"]["schedule"]
            timezone = config["scheduler_config"]["timezone"]
            payload = {"bot": self.bot, "user": self.user, "event_id": event_id}

            Utility.request_event_server(
                EventClass.analytics_pipeline,
                payload,
                is_scheduled=True,
                cron_exp=cron_exp,
                timezone=timezone,
            )
            return event_id

        except Exception as e:
            logger.error(e)
            if event_id:
                AnalyticsPipelineProcessor.delete_task(event_id, self.bot)
            raise AppException(e)


    def _add_one_time_schedule(self, config: Dict):
        """Schedule one-time execution using epoch timestamp."""
        event_id = None

        try:
            run_at = config["scheduler_config"].get("schedule")
            timezone = config["scheduler_config"].get("timezone", "UTC")
            if isinstance(run_at, (int, float)):
                tzinfo = ZoneInfo(timezone) if timezone else ZoneInfo("UTC")
                run_at = datetime.fromtimestamp(run_at, tzinfo)

            event_id = AnalyticsPipelineProcessor.add_scheduled_task(self.bot, self.user, config)

            payload = {"bot": self.bot, "user": self.user, "event_id": event_id}

            Utility.request_event_server(
                EventClass.analytics_pipeline,
                payload,
                is_scheduled=True,
                run_at=run_at.isoformat(),
                timezone=timezone,
            )

            return event_id

        except Exception as e:
            logger.error(e)
            if event_id:
                AnalyticsPipelineProcessor.delete_task(event_id, self.bot)
            raise AppException(e)


    def delete_analytics_event(self, event_id: Text):
        """Delete a scheduled analytics pipeline event."""
        try:
            if not Utility.is_exist(AnalyticsPipelineConfig, raise_error=False, bot=self.bot,
                                    id=event_id, status=True):
                raise AppException("Notification settings not found!")

            Utility.delete_scheduled_event(event_id)
            AnalyticsPipelineProcessor.delete_task(event_id, self.bot)

        except Exception as e:
            logger.error(e)
            raise e


    def _update_schedule(self, event_id: Text, config: Dict):
        settings_updated = False
        current_settings = {}

        try:
            scheduler_config = config.get("scheduler_config")
            if not scheduler_config or not scheduler_config.get("schedule"):
                raise AppException("scheduler_config with a valid schedule is required!")

            current_settings = AnalyticsPipelineProcessor.retrieve_config(event_id, self.bot)
            AnalyticsPipelineProcessor.update_scheduled_task(event_id, self.bot, self.user, config)
            settings_updated = True

            payload = {
                "bot": self.bot,
                "user": self.user,
                "event_id": event_id
            }

            expression_type = scheduler_config.get("expression_type")
            schedule = scheduler_config.get("schedule")
            timezone = scheduler_config.get("timezone")

            if expression_type == "cron":

                Utility.request_event_server(
                    EventClass.analytics_pipeline,
                    payload,
                    method="PUT",
                    is_scheduled=True,
                    cron_exp=schedule,
                    timezone=timezone
                )

            elif expression_type == "epoch":

                epoch_time = int(schedule)
                tzinfo = ZoneInfo(timezone) if timezone else ZoneInfo("UTC")
                run_at = datetime.fromtimestamp(epoch_time, tzinfo)

                scheduler_config["schedule"] = run_at

                Utility.request_event_server(
                    EventClass.analytics_pipeline,
                    payload,
                    method="PUT",
                    is_scheduled=True,
                    run_at=run_at.isoformat(),
                    timezone=timezone
                )

        except Exception as e:
            logger.error(e)
            if settings_updated:
                AnalyticsPipelineProcessor.update_scheduled_task(event_id, self.bot, self.user, current_settings)
            raise e

