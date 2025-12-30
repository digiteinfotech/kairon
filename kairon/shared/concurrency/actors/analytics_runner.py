import json
import sys
import subprocess
from functools import partial
from types import ModuleType
from datetime import datetime, date
from typing import Dict, Optional, Text, Callable

from RestrictedPython import compile_restricted
from loguru import logger

from kairon.exceptions import AppException
from kairon.shared.constants import TriggerCondition

class AnalyticsRunner():

    allowed_builtins = {
        "len": len,
        "range": range,
        "sorted": sorted,
        "min": min,
        "max": max,
        "sum": sum,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "dict": dict,
        "list": list,
        "print": print,
    }

    def execute(self, source_code: Text, predefined_objects: Optional[Dict] = None, **kwargs):
        from kairon.shared.pyscript.callback_pyscript_utils import CallbackScriptUtility
        from kairon.shared.concurrency.actors.utils import PyscriptUtility
        from kairon.shared.pyscript.shared_pyscript_utils import PyscriptSharedUtility
        from kairon.shared.analytics.analytics_pipeline_processor import AnalyticsPipelineProcessor
        predefined_objects = predefined_objects or {}

        try:
            compile_restricted(source_code, filename="<inline>", mode="exec")
        except Exception as e:
            logger.exception(e)
            raise AppException(f"Validation failed: {e}")

        bot = predefined_objects.get("slot", {}).get("bot")

        safe_objects = {
            "add_data": partial(PyscriptSharedUtility.add_data, bot=bot),
            "get_data": partial(PyscriptSharedUtility.get_data, bot=bot),
            "delete_data": partial(PyscriptSharedUtility.delete_data, bot=bot),
            "update_data": partial(PyscriptSharedUtility.update_data, bot=bot),
            "add_data_analytics": partial(CallbackScriptUtility.add_data_analytics, bot=bot),
            "get_data_analytics": partial(CallbackScriptUtility.get_data_analytics, bot=bot),
            "mark_as_processed": partial(CallbackScriptUtility.mark_as_processed, bot=bot),
            "update_data_analytics": partial(CallbackScriptUtility.update_data_analytics, bot=bot),
            "delete_data_analytics": partial(CallbackScriptUtility.delete_data_analytics, bot=bot),
            "srtp_time": PyscriptUtility.srtptime,
            "srtf_time": PyscriptUtility.srtftime,
            "url_parse": PyscriptUtility.url_parse_quote_plus,
            "__builtins__": self.allowed_builtins,
        }

        input_payload = json.dumps({
            "source_code": source_code,
            "safe_globals": list(safe_objects.keys()),
            "predefined_objects":predefined_objects,
            "bot": bot,
        }, default=str)
        action = predefined_objects.get("config", {})
        try:
            process = subprocess.Popen(
                [sys.executable, "-m", "kairon.shared.pyscript.analytics_worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            stdout, stderr = process.communicate(input=input_payload, timeout=600)

            if process.returncode != 0:
                raise AppException(f"Subprocess error: {stdout.strip()}")

            triggers = action.get("triggers")
            if triggers is not None:
                for trigger in triggers:
                    if trigger.get("conditions") == TriggerCondition.success.value and trigger.get(
                            "action_type") == "email_action" and trigger.get("action_name"):
                        action_name = trigger.get("action_name")
                        AnalyticsPipelineProcessor.trigger_email(action_name, bot)

            result = json.loads(stdout)
            return self.__cleanup(result)

        except Exception as e:
            msg = stdout.strip() if 'stdout' in locals() and stdout else str(e)
            logger.exception(msg)
            triggers = action.get("triggers")
            if triggers is not None:
                for trigger in triggers:
                    if trigger.get("conditions") == TriggerCondition.failure.value and trigger.get(
                            "action_type") == "email_action" and trigger.get("action_name"):
                        try:
                            action_name = trigger.get("action_name")
                            AnalyticsPipelineProcessor.trigger_email(action_name, bot)
                        except Exception:
                            logger.exception("Failure email failed")

            raise AppException(f"Execution error: {msg}") from e
    def __cleanup(self, values: Dict):
        clean = {}
        for k, v in values.items():
            if isinstance(v, Callable) or isinstance(v, ModuleType):
                continue
            if isinstance(v, datetime):
                v = v.isoformat()
            elif isinstance(v, date):
                v = v.isoformat()
            clean[k] = v
        return clean
