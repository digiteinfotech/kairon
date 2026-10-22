"""API-facing operations for the lead-qualification prompt and the analytics job status."""
from datetime import datetime
from typing import Any, Dict, List, Optional, Text

from kairon.crm.analytics.models import (
    CRMLeadAnalysisRecord, CRMLeadAnalysisState, CRMLeadPromptRevision, CRMLeadQualificationConfig,
    LeadRecordStatus, MAX_PROMPT_LENGTH,
)
from kairon.crm.analytics.pipeline_manager import CRMLeadPipelineManager
from kairon.crm.analytics.qualifier import qualify
from kairon.exceptions import AppException
from kairon.shared.data.processor import MongoProcessor

MAX_TEST_TURNS = 30
MAX_TEST_TEXT = 1000


class LeadQualificationProcessor:

    @staticmethod
    def _require_crm(bot: Text):
        if not MongoProcessor.is_crm_enabled(bot):
            raise AppException("CRM integration is not enabled")

    @staticmethod
    def _clean_prompt(prompt: Optional[Text]) -> Text:
        prompt = (prompt or "").strip()
        if not prompt:
            raise AppException("Lead qualification prompt cannot be empty")
        if len(prompt) > MAX_PROMPT_LENGTH:
            raise AppException(f"Lead qualification prompt must be at most {MAX_PROMPT_LENGTH} characters")
        return prompt

    @staticmethod
    def _view(config: CRMLeadQualificationConfig) -> Dict[Text, Any]:
        return {"prompt": config.prompt, "version": config.version, "enabled": config.enabled,
                "min_confidence": config.min_confidence, "updated_by": config.user,
                "updated_at": config.timestamp.isoformat() if config.timestamp else None}

    @classmethod
    def get_prompt(cls, bot: Text) -> Optional[Dict[Text, Any]]:
        config = CRMLeadQualificationConfig.objects(bot=bot).first()
        if not config:
            return None
        view = cls._view(config)
        pipeline = CRMLeadPipelineManager.get(bot)
        view["pipeline"] = {"scheduled": pipeline is not None, "event_id": str(pipeline.id) if pipeline else None}
        return view

    @classmethod
    def save_prompt(cls, bot: Text, user: Text, prompt: Text, enabled: bool = True,
                    min_confidence: float = 0.7) -> Dict[Text, Any]:
        cls._require_crm(bot)
        prompt = cls._clean_prompt(prompt)
        if not 0.0 <= float(min_confidence) <= 1.0:
            raise AppException("min_confidence must be between 0 and 1")
        config = CRMLeadQualificationConfig.objects(bot=bot).first()
        if config is None:
            config = CRMLeadQualificationConfig(bot=bot, prompt=prompt, version=1, user=user)
        elif config.prompt != prompt:
            config.prompt = prompt
            config.version = (config.version or 0) + 1
        config.enabled = bool(enabled)
        config.min_confidence = float(min_confidence)
        config.user = user
        config.timestamp = datetime.utcnow()
        config.save()
        if not CRMLeadPromptRevision.objects(bot=bot, version=config.version).first():
            CRMLeadPromptRevision(bot=bot, version=config.version, prompt=prompt, user=user).save()
        view = cls._view(config)
        # The schedule follows the prompt: enabled => the bot's Analytics Pipeline exists, disabled => it is removed.
        view["pipeline"] = (CRMLeadPipelineManager.ensure(bot, user) if config.enabled
                            else CRMLeadPipelineManager.remove(bot, user))
        return view

    @classmethod
    def list_revisions(cls, bot: Text, limit: int = 20) -> List[Dict[Text, Any]]:
        rows = CRMLeadPromptRevision.objects(bot=bot).order_by("-version").limit(min(max(limit, 1), 50))
        return [{"version": r.version, "prompt": r.prompt, "user": r.user, "timestamp": r.timestamp.isoformat()} for r in rows]

    @classmethod
    def test_prompt(cls, bot: Text, user: Text, prompt: Optional[Text], conversation: List[Dict[Text, Text]]) -> Dict[Text, Any]:
        """Runs the real qualifier on a sample transcript. Never writes a record and never contacts ERPNext."""
        cls._require_crm(bot)
        if prompt is None:
            config = CRMLeadQualificationConfig.objects(bot=bot).first()
            if not config:
                raise AppException("No lead qualification prompt has been saved for this bot.")
            prompt = config.prompt
        prompt = cls._clean_prompt(prompt)
        if not conversation or len(conversation) > MAX_TEST_TURNS:
            raise AppException(f"Provide between 1 and {MAX_TEST_TURNS} conversation turns.")
        turns = [{"user": str(t.get("user") or "")[:MAX_TEST_TEXT], "bot": str(t.get("bot") or "")[:MAX_TEST_TEXT]}
                 for t in conversation]
        result, fields = qualify(bot, user, prompt, turns)
        return {"qualifies_as_lead": result.qualifies_as_lead, "confidence": result.confidence,
                "reason": result.reason, "lead_fields": fields.dict(), "dispatched": False}

    @classmethod
    def job_status(cls, bot: Text) -> Dict[Text, Any]:
        state = CRMLeadAnalysisState.objects(bot=bot).first()
        counts = {s.value: CRMLeadAnalysisRecord.objects(bot=bot, status=s.value).count() for s in LeadRecordStatus}
        return {
            "last_run_at": state.last_run_at.isoformat() if state and state.last_run_at else None,
            "last_run_stats": dict(state.last_run_stats) if state and state.last_run_stats else {},
            "last_error": state.last_error if state else None,
            "watermark": state.watermark if state else None,
            "counts": counts,
        }

    @classmethod
    def failed_leads(cls, bot: Text, limit: int = 50) -> List[Dict[Text, Any]]:
        rows = CRMLeadAnalysisRecord.objects(bot=bot, status=LeadRecordStatus.FAILED_PERMANENT.value) \
            .order_by("-updated_at").limit(min(max(limit, 1), 200))
        return [{"sender_id": r.sender_id, "attempts": r.attempts, "last_error": r.last_error,
                 "prompt_version": r.prompt_version, "updated_at": r.updated_at.isoformat()} for r in rows]

    @classmethod
    def retry_failed(cls, bot: Text) -> Dict[Text, int]:
        """Puts dead-lettered rows back in the retry queue (attempts reset). Does not call anything itself."""
        cls._require_crm(bot)
        count = CRMLeadAnalysisRecord.objects(bot=bot, status=LeadRecordStatus.FAILED_PERMANENT.value).update(
            set__status=LeadRecordStatus.ANALYSIS_FAILED.value, set__attempts=0, set__next_attempt_at=datetime.utcnow(),
            set__updated_at=datetime.utcnow())
        return {"requeued": count}
