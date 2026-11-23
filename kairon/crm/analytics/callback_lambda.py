"""
Calls the callback Lambda (the `pyscript_evaluator` function, repo `pyscript-callback`) with a small script.

The lead qualifier uses it to run `process_instruction`, which lives on the Lambda, so Kairon itself holds no LLM-calling code
for this feature. This does not go through `CloudUtility.trigger_lambda`: that records every request and response in the
`ExecutorLogs` collection, and here they hold a conversation excerpt and the lead's contact details, which have a retention
rule of their own. Nothing in the request or the answer is logged here, and error messages carry no payload.
"""
import json
from typing import Any, Dict, Text

from boto3 import Session
from botocore.config import Config

from kairon.exceptions import AppException
from kairon.shared.constants import EventClass
from kairon.shared.utils import Utility

DEFAULT_REGION = "us-east-1"


def callback_lambda_name() -> Text:
    """The configured function name (PYSCRIPT_TASK_DEFINITION); empty when this deployment has none."""
    return str(((Utility.environment.get("events") or {}).get("task_definition") or {}).get(EventClass.pyscript_evaluator) or "")


def run_script(source_code: Text, predefined_objects: Dict[Text, Any], timeout_seconds: int = 60) -> Any:
    """
    Runs `source_code` on the Lambda with `predefined_objects` and returns the script's `bot_response`.
    Raises AppException (never with request or answer text in the message) when the Lambda is not configured, cannot be
    reached, or reports an error.
    """
    function = callback_lambda_name()
    if not function:
        raise AppException("The callback Lambda (PYSCRIPT_TASK_DEFINITION) is not configured.")
    region = ((Utility.environment.get("events") or {}).get("executor") or {}).get("region") or DEFAULT_REGION
    client = Session().client("lambda", region_name=region, config=Config(
        read_timeout=int(timeout_seconds) + 15, connect_timeout=10, retries={"max_attempts": 1}))
    try:
        response = client.invoke(
            FunctionName=function, InvocationType="RequestResponse",
            Payload=json.dumps({"source_code": source_code, "predefined_objects": predefined_objects}).encode(),
        )
        payload = json.loads(response["Payload"].read())
    except Exception as e:
        raise AppException(f"Callback Lambda request failed: {type(e).__name__}")
    finally:
        client.close()
    status = payload.get("statusCode") if isinstance(payload, dict) else None
    if response.get("FunctionError") or status != 200:
        raise AppException(f"The callback Lambda reported an error (status {status}).")
    body = payload.get("body")
    return body.get("bot_response") if isinstance(body, dict) else None
