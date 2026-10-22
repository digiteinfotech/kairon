"""
Scheduled lead analysis. One `run_cycle()` is a bounded, idempotent pass over every CRM-enabled bot; it is safe to run
every five minutes, from any number of workers, and to be killed at any point.

Coordination: a per-bot lease in Mongo (atomic upsert) makes overlapping runs and multiple replicas skip a bot that is
already being processed. Progress is a per-bot watermark plus a per-sender record, so a run never re-sends old
conversations to the LLM, a retry never creates a second Lead (stable event id, and the connector also dedupes on the
conversation id), and one tenant failing never blocks the next.
"""
import hashlib
import socket
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Text

from loguru import logger
from mongoengine import NotUniqueError

from kairon.crm.analytics.models import (
    CRMLeadAnalysisRecord, CRMLeadAnalysisState, CRMLeadQualificationConfig, LeadRecordStatus,
)
from kairon.crm.analytics.qualifier import format_transcript, qualify
from kairon.crm.analytics.source import ConversationSource
from kairon.crm.lead_dispatch import resolve_lead_target
from kairon.crm.models import CRMClientDetails, CRMOnboardingStatus
from kairon.events.publisher import KaironEvent, KaironEventPublisher
from kairon.exceptions import AppException
from kairon.shared.utils import Utility

DEFAULTS = {
    "batch_size": 50,               # senders analysed per bot per cycle
    "retry_batch_size": 25,         # failed/pending records re-tried per bot per cycle
    "idle_seconds": 120,            # a conversation is analysed once it has been quiet this long
    "lookback_seconds": 900,        # re-scan this far behind the watermark to catch late-written messages
    "initial_backfill_seconds": 3600,
    "max_history_turns": 40,
    "max_transcript_chars": 6000,
    "lease_seconds": 600,
    "time_budget_seconds": 420,     # stop starting new analyses; the PyScript subprocess is hard-limited to 600 s
    "max_attempts": 5,
    "backoff_base_seconds": 60,
    "backoff_cap_seconds": 3600,
}
TRANSIENT_HTTP = {408, 409, 425, 429}


def cfg(key: Text):
    return ((Utility.environment.get("crm") or {}).get("lead_analysis") or {}).get(key, DEFAULTS[key])


def lead_event_id(bot: Text, sender_id: Text) -> Text:
    """Deterministic per user: the same qualification always has the same event id, so a retry is a duplicate."""
    return "evt_lead_" + hashlib.sha256(f"{bot}\x00{sender_id}".encode("utf-8")).hexdigest()[:32]


class LeadAnalysisPipeline:

    def __init__(self, worker_id: Optional[Text] = None, now_fn=time.time):
        self.worker_id = worker_id or f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
        self.now_fn = now_fn

    # ------------------------------------------------------------------ cycle

    def run_cycle(self) -> Dict[Text, Any]:
        summary: Dict[Text, Any] = {"bots": 0, "skipped_leased": 0, "failed_bots": 0, "analysed": 0, "qualified": 0,
                                    "dispatched": 0, "errors": 0}
        bots = [c.bot for c in CRMLeadQualificationConfig.objects(enabled=True).only("bot")]
        for bot in bots:
            try:
                stats = self.run_bot(bot)
            except Exception as e:  # one tenant must never stop the others
                logger.exception(f"[LeadAnalysis] bot={bot} failed: {type(e).__name__}")
                summary["failed_bots"] += 1
                CRMLeadAnalysisState.objects(bot=bot).update_one(upsert=True, set__last_error=f"{type(e).__name__}: {e}"[:300])
                continue
            if stats is None:
                summary["skipped_leased"] += 1
                continue
            summary["bots"] += 1
            for key in ("analysed", "qualified", "dispatched", "errors"):
                summary[key] += stats.get(key, 0)
        return summary

    def _acquire(self, bot: Text) -> bool:
        now = datetime.utcfromtimestamp(self.now_fn())
        until = now + timedelta(seconds=cfg("lease_seconds"))
        try:
            CRMLeadAnalysisState.objects(bot=bot).filter(
                __raw__={"$or": [{"lease_until": None}, {"lease_until": {"$lt": now}}]}
            ).update_one(upsert=True, set__lease_owner=self.worker_id, set__lease_until=until)
        except NotUniqueError:
            return False  # the row exists and another worker's unexpired lease did not match the filter
        state = CRMLeadAnalysisState.objects(bot=bot).first()
        return bool(state and state.lease_owner == self.worker_id)

    def _release(self, bot: Text, **fields):
        CRMLeadAnalysisState.objects(bot=bot, lease_owner=self.worker_id).update_one(
            set__lease_until=None, unset__lease_owner=True, **fields)

    # ------------------------------------------------------------------ per bot

    def run_bot(self, bot: Text) -> Optional[Dict[Text, int]]:
        from kairon.shared.data.processor import MongoProcessor
        if not MongoProcessor.is_crm_enabled(bot):
            return {}                       # CRM switched off for the bot: nothing is analysed or sent
        config = CRMLeadQualificationConfig.objects(bot=bot, enabled=True).first()
        crm = CRMClientDetails.objects(bot=bot).first()
        if not config or not crm or crm.onboarding_status != CRMOnboardingStatus.COMPLETED.value or not crm.site_name:
            return {}
        if not self._acquire(bot):
            return None
        stats = {"analysed": 0, "qualified": 0, "dispatched": 0, "errors": 0, "senders": 0}
        error = None
        try:
            now = self.now_fn()
            state = CRMLeadAnalysisState.objects(bot=bot).first()
            until = now - cfg("idle_seconds")
            watermark = state.watermark or (now - cfg("initial_backfill_seconds"))
            after = max(0.0, watermark - cfg("lookback_seconds"))
            batch = cfg("batch_size")
            page_size = max(batch * 2, 100)
            cursor, seen, work, last_done_ts, exhausted = after, set(), 0, None, False
            started = time.monotonic()
            out_of_time = lambda: time.monotonic() - started > cfg("time_budget_seconds")  # noqa: E731
            while work < batch and not out_of_time():
                page = ConversationSource.changed_senders(bot, cursor, until, page_size, inclusive=cursor != after)
                fresh = [(sid, ts) for sid, ts in page if sid not in seen]
                records = {r.sender_id: r for r in CRMLeadAnalysisRecord.objects(
                    bot=bot, sender_id__in=[sid for sid, _ in fresh])}
                for sender_id, last_ts in fresh:
                    seen.add(sender_id)
                    stats["senders"] += 1
                    if self._process_sender(bot, sender_id, last_ts, until, config, crm, stats, records.get(sender_id)):
                        work += 1
                    last_done_ts = last_ts
                    if work >= batch or out_of_time():
                        break
                if work >= batch or out_of_time():
                    break
                if len(page) < page_size:
                    exhausted = True
                    break
                # a full page of senders we have already seen would never advance: step past the shared timestamp
                cursor = page[-1][1] if fresh else page[-1][1] + 1e-6
            for record in ([] if out_of_time() else self._due_retries(bot, seen)):
                if out_of_time():
                    break
                self._process_sender(bot, record.sender_id, record.last_message_ts, until, config, crm, stats, record)
            new_mark = until if exhausted else (last_done_ts or watermark)
            watermark = max(watermark, new_mark)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"[:300]
            raise
        finally:
            fields = {"set__last_run_at": datetime.utcnow(), "set__last_run_stats": stats}
            if error:
                fields["set__last_error"] = error
            else:
                fields["set__watermark"] = watermark
                fields["unset__last_error"] = True
            self._release(bot, **fields)
        return stats

    def _due_retries(self, bot: Text, already: set):
        now = datetime.utcfromtimestamp(self.now_fn())
        rows = CRMLeadAnalysisRecord.objects(
            bot=bot,
            status__in=[LeadRecordStatus.QUALIFIED.value, LeadRecordStatus.ANALYSIS_FAILED.value],
            next_attempt_at__lte=now,
        ).order_by("next_attempt_at").limit(cfg("retry_batch_size"))
        return [r for r in rows if r.sender_id not in already]

    # ------------------------------------------------------------------ per sender

    def _process_sender(self, bot, sender_id, last_ts, until, config, crm, stats, record=None) -> bool:
        """Returns True when it spent real work (an LLM call or a delivery attempt), which is what batches count."""
        try:
            if record and record.status in (LeadRecordStatus.DISPATCHED.value, LeadRecordStatus.FAILED_PERMANENT.value):
                return False
            has_new_messages = (not record) or last_ts > (record.last_message_ts or 0)
            if record and not has_new_messages and record.status in (
                LeadRecordStatus.UNQUALIFIED.value, LeadRecordStatus.NEEDS_CONTACT.value
            ):
                return False
            if record is None:
                record = CRMLeadAnalysisRecord(bot=bot, sender_id=sender_id, status=LeadRecordStatus.ANALYSIS_FAILED.value)

            if record.status == LeadRecordStatus.QUALIFIED.value and not has_new_messages and record.lead_fields:
                self._dispatch(bot, record, crm, None, stats)   # delivery retry: no second LLM call
                return True

            turns = ConversationSource.history(bot, sender_id, until, cfg("max_history_turns"))
            if not turns:
                return False
            record.last_message_ts = max(t["ts"] for t in turns)
            stats["analysed"] += 1
            try:
                result, fields = qualify(bot, "crm_lead_analysis", config.prompt, turns)
            except AppException as e:
                self._fail(record, str(e), stats, analysis=True)
                return True
            record.prompt_version = config.version
            record.confidence = result.confidence
            record.reason = result.reason
            record.attempts = 0
            record.last_error = None
            if not (result.qualifies_as_lead and result.confidence >= config.min_confidence):
                record.status = LeadRecordStatus.UNQUALIFIED.value
                record.lead_fields = {}
                self._save(record)
                return True
            record.lead_fields = {k: v for k, v in fields.dict().items() if v}
            if not (fields.email or fields.phone):
                record.status = LeadRecordStatus.NEEDS_CONTACT.value   # re-evaluated when the user writes again
                self._save(record)
                return True
            record.status = LeadRecordStatus.QUALIFIED.value
            stats["qualified"] += 1
            self._save(record)
            self._dispatch(bot, record, crm, turns, stats)
            return True
        except Exception as e:  # a single user must not abort the batch
            stats["errors"] += 1
            logger.exception(f"[LeadAnalysis] bot={bot} sender processing failed: {type(e).__name__}")
            return True

    def _dispatch(self, bot, record, crm, turns, stats):
        if turns is None:
            turns = ConversationSource.history(bot, record.sender_id, record.last_message_ts, cfg("max_history_turns"))
        transcript = format_transcript(turns, cfg("max_transcript_chars"))
        lf = record.lead_fields or {}
        name = " ".join(p for p in (lf.get("first_name"), lf.get("last_name")) if p)
        event = KaironEvent(
            event_type="lead.qualified",
            event_id=lead_event_id(bot, record.sender_id),
            payload={
                "bot_id": bot,
                "conversation_id": record.sender_id,
                "summary": f"Qualified by AI analysis: {record.reason or ''}"[:500],
                "transcript": transcript,
                "lead_data": {"name": name, "first_name": lf.get("first_name") or "", "last_name": lf.get("last_name") or "",
                              "email": lf.get("email") or "", "phone": lf.get("phone") or "", "company": lf.get("company") or ""},
                "qualification_score": int(round((record.confidence or 0) * 100)),
                "intent": "", "budget": "", "industry": "",
            },
        )
        try:
            url, secret = resolve_lead_target(bot, crm.site_name)
            outcome = KaironEventPublisher.publish_webhook(url, secret, event, timeout_seconds=15)
        except Exception as e:
            self._fail(record, f"dispatch: {type(e).__name__}", stats)
            return
        status = outcome.get("status_code")
        if outcome.get("success"):
            record.status = LeadRecordStatus.DISPATCHED.value
            record.event_id = event.event_id
            record.dispatched_at = datetime.utcnow()
            record.next_attempt_at = None
            record.last_error = None
            stats["dispatched"] += 1
            self._save(record)
        elif status in TRANSIENT_HTTP or (status or 0) >= 500:
            self._fail(record, f"dispatch: HTTP {status}", stats)
        else:
            self._fail(record, f"dispatch rejected: HTTP {status}", stats, permanent=True)

    # ------------------------------------------------------------------ bookkeeping

    def _fail(self, record, message, stats, analysis=False, permanent=False):
        record.attempts = (record.attempts or 0) + 1
        record.last_error = message[:300]
        stats["errors"] += 1
        if analysis:
            record.status = LeadRecordStatus.ANALYSIS_FAILED.value
        if permanent or record.attempts >= cfg("max_attempts"):
            record.status = LeadRecordStatus.FAILED_PERMANENT.value
            record.next_attempt_at = None
        else:
            delay = min(cfg("backoff_base_seconds") * (2 ** (record.attempts - 1)), cfg("backoff_cap_seconds"))
            record.next_attempt_at = datetime.utcfromtimestamp(self.now_fn()) + timedelta(seconds=delay)
        self._save(record)

    @staticmethod
    def _save(record):
        record.updated_at = datetime.utcnow()
        record.save()
