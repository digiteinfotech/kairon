"""
Reference job documents captured from today's schedule_action direct write
(tests/testing_data/schedule_reference_jobs/*.json, produced by
tests/parity/capture_schedule_reference_jobs.py).
"""
import base64
import json
import os
import pickle

import pytest

os.environ["system_file"] = "./tests/testing_data/system.yaml"

from tests.parity import capture_schedule_reference_jobs as capture_module  # noqa: E402


def load(case_type):
    with open(capture_module.fixture_path(case_type), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def regenerated():
    return {case_type: capture_module.capture(case_type) for case_type in capture_module.CASES}


@pytest.mark.parametrize("case_type", ["pyscript", "flow"])
def test_stored_fixture_matches_direct_write(case_type, regenerated):
    """Re-running today's schedule_action code path reproduces the stored fixture exactly."""
    stored_text = open(capture_module.fixture_path(case_type), encoding="utf-8").read()
    assert capture_module.dumps(regenerated[case_type]) == stored_text


@pytest.mark.parametrize("case_type", ["pyscript", "flow"])
def test_document_shape(case_type):
    fixture = load(case_type)
    doc = fixture["document"]
    job_id = fixture["inputs"]["fixed_job_id"]
    assert list(doc.keys()) == ["_id", "next_run_time", "job_state"]
    assert doc["_id"] == job_id
    assert set(doc["next_run_time"].keys()) == {"$numberDouble"}
    assert doc["job_state"]["$binary"]["base64"] == fixture["job_state_pickle_base64"]
    assert fixture["dispatch_call"]["method"] == "GET"
    assert fixture["dispatch_call"]["path"] == f"/api/events/dispatch/{job_id}"
    from kairon.shared.utils import Utility
    Utility.load_environment()
    assert fixture["job_store"] == {"database": Utility.environment["events"]["queue"]["name"],
                                    "collection": Utility.environment["events"]["scheduler"]["collection"]}


@pytest.mark.parametrize("case_type", ["pyscript", "flow"])
def test_job_state_defaults(case_type):
    fixture = load(case_type)
    job = pickle.loads(base64.b64decode(fixture["job_state_pickle_base64"]))
    assert job["id"] == fixture["inputs"]["fixed_job_id"]
    assert job["version"] == 1
    assert job["executor"] == "default"
    assert job["name"] == "execute_task"
    assert job["misfire_grace_time"] == 7200
    assert job["coalesce"] is True
    assert job["max_instances"] == 1
    assert job["trigger"].run_date.isoformat() == "2030-01-15T10:30:00+05:30"
    assert job["next_run_time"] == job["trigger"].run_date
    assert float(fixture["document"]["next_run_time"]["$numberDouble"]) == job["next_run_time"].timestamp()
    assert fixture["decoded_job_state"]["next_run_time"] == "2030-01-15T10:30:00+05:30"
    assert fixture["decoded_job_state"]["trigger"] == {
        "__trigger__": "apscheduler.triggers.date.DateTrigger",
        "run_date": "2030-01-15T10:30:00+05:30", "timezone": "Asia/Kolkata"}


def test_pyscript_job_function_and_args():
    from apscheduler.util import obj_to_ref
    from kairon.events.executors.factory import ExecutorFactory
    from kairon.shared.constants import EventExecutor

    fixture = load("pyscript")
    job = pickle.loads(base64.b64decode(fixture["job_state_pickle_base64"]))
    callback_ref = obj_to_ref(ExecutorFactory.get_executor(EventExecutor.callback).execute_task)
    assert job["func"] == callback_ref
    assert job["args"][0] == callback_ref
    assert job["args"][1] == "scheduler_evaluator"
    assert job["args"][2] == {
        "source_code": "bot_response = 'hello world'",
        "predefined_objects": {"user": "1011", "order_id": "A-77", "bot": "6697add6b8e47524eb983374",
                               "event": fixture["inputs"]["fixed_job_id"]},
    }
    assert job["kwargs"] == {"task_type": "Action"}
    assert fixture["decoded_job_state"]["func"] == callback_ref


def test_flow_job_function_and_args():
    fixture = load("flow")
    job = pickle.loads(base64.b64decode(fixture["job_state_pickle_base64"]))
    assert job["func"] == "kairon.events.executors.lamda:LambdaExecutor.execute_task"
    assert type(job["args"][0]).__name__ == "LambdaExecutor"
    assert job["args"][1] == "agentic_flow"
    assert job["args"][2] == {
        "slot_data": json.dumps({"user": "1011", "order_id": "A-77", "bot": "6697add6b8e47524eb983374"}),
        "flow_name": "reference_flow",
        "bot": "6697add6b8e47524eb983374",
        "user": "default",
    }
    assert job["kwargs"] == {"task_type": "Event"}
    assert fixture["decoded_job_state"]["args"][0]["__object__"].endswith("LambdaExecutor")


@pytest.mark.parametrize("case_type", ["pyscript", "flow"])
def test_equivalent_request_is_valid_schedule_request(case_type):
    from kairon.events.models import ScheduleActionRequest

    request = ScheduleActionRequest.from_payload(load(case_type)["equivalent_schedule_request"])
    assert request.schedule_action_type == case_type
    assert request.job_id == load(case_type)["inputs"]["fixed_job_id"]
