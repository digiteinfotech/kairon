"""
Creates and removes the per-bot Analytics Pipeline that runs CRM lead qualification.

The pipeline is an ordinary Analytics Pipeline: a PyScript callback (`CallbackConfig`) scheduled by the existing
pipeline event (`AnalyticsPipelineEvent`, cron on the event server). The script is one line that calls the
`analyse_crm_leads` helper, which runs the lease-protected analysis for the calling bot only. Nothing here talks to the
LLM; the analysis uses the pipeline's own LLM entry point (see qualifier.invoke_llm).
"""
from datetime import datetime
from typing import Dict, Text

from loguru import logger

from kairon.events.definitions.analytic_pipeline_handler import AnalyticsPipelineEvent
from kairon.shared.actions.data_objects import AnalyticsPipelineConfig
from kairon.shared.callback.data_objects import CallbackConfig
from kairon.shared.constants import EventRequestType
from kairon.shared.data.data_models import AnalyticsPipelineEventRequest

PIPELINE_NAME = "crm_lead_qualification"
CALLBACK_NAME = "crm_lead_qualification"
CRON = "*/5 * * * *"
SCRIPT = "bot_response = analyse_crm_leads()\n"


class CRMLeadPipelineManager:

    @staticmethod
    def get(bot: Text):
        return AnalyticsPipelineConfig.objects(bot=bot, pipeline_name=PIPELINE_NAME, status=True).first()

    @classmethod
    def ensure(cls, bot: Text, user: Text) -> Dict:
        """Idempotent: creates the callback and the five-minute schedule once per bot."""
        try:
            existing = cls.get(bot)
            if existing:
                return {"scheduled": True, "event_id": str(existing.id), "created": False}
            if not CallbackConfig.objects(bot=bot, name=CALLBACK_NAME).first():
                CallbackConfig.create_entry(bot, CALLBACK_NAME, SCRIPT, expire_in=0)
            request = AnalyticsPipelineEventRequest(
                pipeline_name=PIPELINE_NAME, callback_name=CALLBACK_NAME, timestamp=datetime.utcnow().isoformat(),
                scheduler_config={"expression_type": "cron", "schedule": CRON, "timezone": "UTC"},
            )
            event = AnalyticsPipelineEvent(bot, user)
            event.callback_name = CALLBACK_NAME
            event.validate()
            event_id = event.enqueue(EventRequestType.add_schedule.value, config=request.dict())
            return {"scheduled": True, "event_id": event_id, "created": True}
        except Exception as e:
            # The prompt is saved either way; the caller reports why the schedule is missing.
            logger.error(f"[CRMLeadPipeline] could not schedule for bot={bot}: {type(e).__name__}: {e}")
            return {"scheduled": False, "error": str(e)[:300]}

    @classmethod
    def remove(cls, bot: Text, user: Text) -> Dict:
        existing = cls.get(bot)
        if not existing:
            return {"scheduled": False}
        try:
            AnalyticsPipelineEvent(bot, user).delete_schedule(str(existing.id))
            return {"scheduled": False}
        except Exception as e:
            logger.error(f"[CRMLeadPipeline] could not unschedule bot={bot}: {type(e).__name__}")
            return {"scheduled": True, "error": str(e)[:300]}
