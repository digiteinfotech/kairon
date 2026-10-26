"""
Capture reference scheduler job documents from today's schedule_action direct write.

Runs the real ActionSchedule.execute() code path (kairon/actions/definitions/schedule.py)
for one pyscript and one flow schedule action against mongomock, with only the
non-deterministic or networked edges pinned:
  * uuid7() in the schedule module returns a fixed job id
  * the job-store MongoClient is a mongomock client
  * the GET /api/events/dispatch/{id} wake call is answered by a stub

The job document exactly as __save_job inserted it ({_id, next_run_time,
job_state: Binary(pickle)}) is stored with the pickle base64-encoded, together with
a decoded, human-readable view of job_kwargs. These are the baseline the events
schedule endpoint's jobs are compared against (events-schedule-api R1, R2).

Regenerate:
    PYTHONPATH=$PWD .venv310/bin/python tests/parity/capture_schedule_reference_jobs.py
"""
import asyncio
import base64
import json
import os
import pickle
import sys
import uuid
from contextlib import ExitStack
from datetime import datetime
from typing import Any, Dict
from unittest import mock

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "testing_data",
                       "schedule_reference_jobs")
FIXTURE_VERSION = 1

BOT = "6697add6b8e47524eb983374"
USER = "test_user"
SENDER_ID = "default"
EXECUTOR_TYPE = "aws_lambda"

CASES: Dict[str, Dict[str, Any]] = {
    "pyscript": {
        "action_name": "reference_schedule_pyscript",
        "schedule_action": "reference_callback_script",
        "pyscript_code": "bot_response = 'hello world'",
        "schedule_time": "2030-01-15 10:30:00",
        "timezone": "Asia/Kolkata",
        "params": {"user": "1011", "order_id": "A-77"},
        "job_id": "0193a1b2c3d47e5f8a9b0c1d2e3f4a5b",
    },
    "flow": {
        "action_name": "reference_schedule_flow",
        "schedule_action": "reference_flow",
        "schedule_time": "2030-01-15 10:30:00",
        "timezone": "Asia/Kolkata",
        "params": {"user": "1011", "order_id": "A-77"},
        "job_id": "0193a1b2c3d47e5f8a9b0c1d2e3f4a5c",
    },
}


def load_environment():
    os.environ.setdefault("system_file", "./tests/testing_data/system.yaml")
    from kairon.shared.utils import Utility
    Utility.load_environment()
    return Utility


def _tracker():
    from rasa_sdk import Tracker
    return Tracker(
        sender_id=SENDER_ID,
        slots={"bot": BOT},
        latest_message={"text": "remind me", "intent_ranking": [{"name": "reminder"}],
                        "intent": {"name": "reminder"}},
        events=[],
        paused=False,
        followup_action=None,
        active_loop={},
        latest_action_name="action_listen",
    )


def _seed(case_type: str, case: Dict[str, Any]):
    from kairon.shared.actions.data_objects import (
        Actions, ScheduleAction, CustomActionDynamicParameters, CustomActionRequestParameters)
    from kairon.shared.actions.models import ActionType
    from kairon.shared.callback.data_objects import CallbackConfig

    Actions(name=case["action_name"], type=ActionType.schedule_action.value, bot=BOT, user=USER).save()
    if case_type == "pyscript":
        CallbackConfig(name=case["schedule_action"], pyscript_code=case["pyscript_code"],
                       validation_secret="reference", execution_mode="async", bot=BOT).save()
    ScheduleAction(
        name=case["action_name"], bot=BOT, user=USER,
        schedule_time=CustomActionDynamicParameters(parameter_type="value", value=case["schedule_time"]),
        schedule_action=case["schedule_action"],
        schedule_action_type=case_type,
        timezone=case["timezone"],
        response_text="Action schedule",
        params_list=[CustomActionRequestParameters(key=k, parameter_type="value", value=v, encrypt=False)
                     for k, v in case["params"].items()],
    ).save()


def describe(value: Any) -> Any:
    """Human-readable, JSON-safe rendering of an unpickled job_kwargs value."""
    from apscheduler.triggers.date import DateTrigger
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, DateTrigger):
        return {"__trigger__": "apscheduler.triggers.date.DateTrigger",
                "run_date": value.run_date.isoformat(), "timezone": str(value.run_date.tzinfo)}
    if isinstance(value, dict):
        return {str(k): describe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [describe(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "value") and type(value).__module__ != "builtins" and isinstance(value.value, str):
        return {"__enum__": f"{type(value).__module__}.{type(value).__qualname__}", "value": value.value}
    return {"__object__": f"{type(value).__module__}.{type(value).__qualname__}",
            "state": describe(getattr(value, "__dict__", {}))}


def capture(case_type: str) -> Dict[str, Any]:
    """Run ActionSchedule.execute for one case and return the reference fixture."""
    import mongomock
    from mongoengine import connect, disconnect
    from rasa_sdk.executor import CollectingDispatcher
    from bson import json_util

    Utility = load_environment()
    from kairon.actions.definitions import schedule as schedule_module
    from kairon.actions.definitions.schedule import ActionSchedule

    case = CASES[case_type]
    events_db = Utility.environment["events"]["queue"]["name"]
    job_store = Utility.environment["events"]["scheduler"]["collection"]
    job_client = mongomock.MongoClient()
    dispatch = mock.AsyncMock(return_value=({"success": True, "message": "Scheduled event dispatch!",
                                             "data": None, "error_code": 0}, 200, None, None))

    disconnect()
    connect("reference_jobs", host="mongodb://localhost", mongo_client_class=mongomock.MongoClient)
    try:
        _seed(case_type, case)
        env = Utility.environment.copy()
        env["events"] = {**env["events"], "executor": {**env["events"]["executor"], "type": EXECUTOR_TYPE}}
        with ExitStack() as stack:
            stack.enter_context(mock.patch.dict(Utility.environment, env))
            stack.enter_context(mock.patch.object(schedule_module, "uuid7",
                                                  return_value=uuid.UUID(hex=case["job_id"])))
            stack.enter_context(mock.patch.object(ActionSchedule, "_ActionSchedule__client", job_client))
            stack.enter_context(mock.patch.object(schedule_module.ActionUtility, "execute_request_async",
                                                  dispatch))
            dispatcher = CollectingDispatcher()
            asyncio.run(ActionSchedule(BOT, case["action_name"]).execute(dispatcher, _tracker(), {}))

            from kairon.shared.actions.data_objects import ActionServerLogs
            log = ActionServerLogs.objects(action=case["action_name"]).get()
            if log.status != "Success":
                raise RuntimeError(f"schedule_action failed: {log.exception}")

            docs = list(job_client[events_db][job_store].find())
            if len(docs) != 1:
                raise RuntimeError(f"expected exactly one job document, found {len(docs)}")
            doc = docs[0]
            job_kwargs = pickle.loads(doc["job_state"])
            dispatch_url = dispatch.call_args.args[0]
            dispatch_method = dispatch.call_args.args[1]
            event_server = Utility.environment["events"]["server_url"]
    finally:
        disconnect()

    schedule_data = dict(case["params"])
    schedule_data["bot"] = BOT
    return {
        "fixture_version": FIXTURE_VERSION,
        "schedule_action_type": case_type,
        "captured_from": "kairon/actions/definitions/schedule.py ActionSchedule.execute -> "
                         "add_schedule_job -> __save_job (direct insert into the job store)",
        "inputs": {
            "bot": BOT,
            "sender_id": SENDER_ID,
            "action_config": {
                "name": case["action_name"],
                "schedule_action_type": case_type,
                "schedule_action": case["schedule_action"],
                "schedule_time": {"parameter_type": "value", "value": case["schedule_time"]},
                "timezone": case["timezone"],
                "params_list": [{"key": k, "parameter_type": "value", "value": v}
                                for k, v in case["params"].items()],
            },
            "callback_pyscript_code": case.get("pyscript_code"),
            "events_executor_type": EXECUTOR_TYPE,
            "fixed_job_id": case["job_id"],
        },
        "equivalent_schedule_request": {
            "job_id": case["job_id"],
            "run_at": datetime.fromisoformat(case["schedule_time"]).isoformat(),
            "timezone": case["timezone"],
            "schedule_action_type": case_type,
            "schedule_action": case["schedule_action"],
            "bot": BOT,
            "user": SENDER_ID,
            "data": schedule_data,
        },
        "job_store": {"database": events_db, "collection": job_store},
        "document": json.loads(json_util.dumps(doc, json_options=json_util.CANONICAL_JSON_OPTIONS)),
        "job_state_pickle_base64": base64.b64encode(bytes(doc["job_state"])).decode("ascii"),
        "decoded_job_state": describe(job_kwargs),
        "dispatch_call": {"method": dispatch_method,
                          "url": dispatch_url,
                          "path": dispatch_url[len(event_server):]},
    }


def fixture_path(case_type: str) -> str:
    return os.path.normpath(os.path.join(OUT_DIR, f"{case_type}_job.json"))


def dumps(fixture: Dict[str, Any]) -> str:
    return json.dumps(fixture, indent=2, ensure_ascii=False) + "\n"


def main(argv=None):
    os.makedirs(OUT_DIR, exist_ok=True)
    for case_type in CASES:
        fixture = capture(case_type)
        with open(fixture_path(case_type), "w", encoding="utf-8") as fh:
            fh.write(dumps(fixture))
        print(f"wrote {fixture_path(case_type)}", flush=True)
    # importing the action server starts pykka actors (non-daemon threads); stop them so the script exits
    from kairon.shared.concurrency.actors.factory import ActorFactory
    for _, proxy in ActorFactory._ActorFactory__actors.items():
        proxy[1].stop()


if __name__ == "__main__":
    sys.exit(main())
