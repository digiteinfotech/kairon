"""
POST /api/events/schedule/action (events-schedule-api R1, R4).

The job document written by the endpoint is compared with the reference documents captured
from schedule_action's direct write (tests/testing_data/schedule_reference_jobs/*.json), using
their `equivalent_schedule_request` bodies. Mongo is mongomock for both mongoengine and the
scheduler job-store client.
"""
import base64
import json
import os
import pickle
from unittest import mock

import mongomock
import pytest
from mongoengine import connect, disconnect

os.environ["system_file"] = "./tests/testing_data/system.yaml"

from kairon.shared.utils import Utility  # noqa: E402

Utility.load_environment()

with mock.patch("pymongo.collection.Collection.create_index"):
    from kairon.events.server import app  # noqa: E402
    from kairon.events.scheduler.kscheduler import KScheduler  # noqa: E402

from starlette.testclient import TestClient  # noqa: E402

REFERENCE_DIR = os.path.join("tests", "testing_data", "schedule_reference_jobs")
ENDPOINT = "/api/events/schedule/action"
EVENTS_DB = Utility.environment["events"]["queue"]["name"]
JOB_STORE = Utility.environment["events"]["scheduler"]["collection"]


def reference(case_type):
    with open(os.path.join(REFERENCE_DIR, f"{case_type}_job.json"), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture()
def job_client():
    client = mongomock.MongoClient()
    with mock.patch.object(KScheduler, "_KScheduler__client", client):
        yield client


@pytest.fixture()
def jobs(job_client):
    return job_client[EVENTS_DB][JOB_STORE]


@pytest.fixture(autouse=True)
def environment():
    """Same executor type the reference documents were captured with; mongomock for mongoengine."""
    fixture = reference("pyscript")
    env = Utility.environment.copy()
    env["events"] = {**env["events"], "executor": {**env["events"]["executor"],
                                                   "type": fixture["inputs"]["events_executor_type"]}}
    disconnect()
    connect("schedule_endpoint_test", host="mongodb://localhost", mongo_client_class=mongomock.MongoClient)
    from kairon.shared.callback.data_objects import CallbackConfig
    CallbackConfig(name=fixture["inputs"]["action_config"]["schedule_action"],
                   pyscript_code=fixture["inputs"]["callback_pyscript_code"],
                   validation_secret="reference", execution_mode="async",
                   bot=fixture["inputs"]["bot"]).save()
    with mock.patch.dict(Utility.environment, env):
        yield
    disconnect()


@pytest.fixture()
def client():
    return TestClient(app)


def assert_error(response, fragment=None):
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == 422
    assert body["data"] is None
    assert isinstance(body["message"], str) and body["message"]
    if fragment:
        assert fragment in body["message"]


def view(value):
    """Structural, type-aware view of an unpickled job_state value (object identity ignored)."""
    from datetime import datetime
    from enum import Enum
    from apscheduler.triggers.date import DateTrigger
    if isinstance(value, DateTrigger):
        return ("DateTrigger", view(value.run_date))
    if isinstance(value, datetime):
        return ("datetime", value.isoformat(), str(value.tzinfo))
    if isinstance(value, Enum):
        return ("enum", type(value).__qualname__, value.value)
    if isinstance(value, dict):
        return ("dict", [(k, view(v)) for k, v in value.items()])
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, [view(v) for v in value])
    if value is None or isinstance(value, (str, int, float, bool)):
        return (type(value).__name__, value)
    return ("object", f"{type(value).__module__}.{type(value).__qualname__}", view(vars(value)))


@pytest.mark.parametrize("case_type", ["pyscript", "flow"])
def test_valid_request_writes_reference_job_document(case_type, client, jobs):
    fixture = reference(case_type)
    request = fixture["equivalent_schedule_request"]

    response = client.post(ENDPOINT, json=request)

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Scheduled action job created!",
                               "data": {"job_id": request["job_id"]}, "error_code": 0}
    docs = list(jobs.find())
    assert len(docs) == 1
    doc = docs[0]
    assert list(doc.keys()) == ["_id", "next_run_time", "job_state"]
    assert doc["_id"] == request["job_id"]
    assert doc["next_run_time"] == float(fixture["document"]["next_run_time"]["$numberDouble"])
    # same keys in the same order, same types and values for func, args, kwargs, trigger,
    # next_run_time and the job defaults
    expected = pickle.loads(base64.b64decode(fixture["job_state_pickle_base64"]))
    assert view(pickle.loads(doc["job_state"])) == view(expected)


def test_pyscript_job_state_is_byte_identical(client, jobs):
    """
    The pyscript reference pickle has no input strings that the capture script shared by identity
    with code literals, so the endpoint's pickle is byte-identical. (The flow reference memoizes
    user 'default' against the interned executor literal 'default', a pickle-memo artifact of the
    capture script's literal sender id; its structure is compared in the test above.)
    """
    fixture = reference("pyscript")
    request = fixture["equivalent_schedule_request"]
    client.post(ENDPOINT, json=request)
    doc = jobs.find_one({"_id": request["job_id"]})
    assert base64.b64encode(bytes(doc["job_state"])).decode("ascii") == fixture["job_state_pickle_base64"]


@pytest.mark.parametrize("case_type", ["pyscript", "flow"])
def test_job_state_fields(case_type, client, jobs):
    fixture = reference(case_type)
    request = fixture["equivalent_schedule_request"]
    client.post(ENDPOINT, json=request)

    job = pickle.loads(jobs.find_one({"_id": request["job_id"]})["job_state"])
    expected = pickle.loads(base64.b64decode(fixture["job_state_pickle_base64"]))
    assert job["id"] == request["job_id"]
    assert job["executor"] == "default"
    assert job["misfire_grace_time"] == 7200
    assert job["coalesce"] is True
    assert job["max_instances"] == 1
    assert job["name"] == "execute_task"
    assert job["func"] == expected["func"]
    assert job["args"][1:] == expected["args"][1:]
    assert job["kwargs"] == expected["kwargs"]
    assert job["trigger"].run_date == expected["trigger"].run_date
    assert str(job["trigger"].run_date.tzinfo) == str(expected["trigger"].run_date.tzinfo)
    assert job["next_run_time"] == expected["next_run_time"]


def test_duplicate_job_id_rejected_without_second_document(client, jobs):
    request = reference("pyscript")["equivalent_schedule_request"]
    assert client.post(ENDPOINT, json=request).json()["success"] is True
    before = list(jobs.find())

    response = client.post(ENDPOINT, json=request)

    assert_error(response, request["job_id"])
    assert list(jobs.find()) == before
    assert jobs.count_documents({}) == 1


def test_duplicate_job_id_across_types_rejected(client, jobs):
    first = reference("pyscript")["equivalent_schedule_request"]
    second = dict(reference("flow")["equivalent_schedule_request"], job_id=first["job_id"])
    client.post(ENDPOINT, json=first)

    assert_error(client.post(ENDPOINT, json=second))
    assert jobs.count_documents({}) == 1


@pytest.mark.parametrize("field", ["job_id", "run_at", "timezone", "schedule_action_type",
                                   "schedule_action", "bot", "user", "data"])
def test_missing_field_rejected(field, client, jobs):
    request = dict(reference("flow")["equivalent_schedule_request"])
    request.pop(field)

    assert_error(client.post(ENDPOINT, json=request), f"{field}: field required")
    assert jobs.count_documents({}) == 0


@pytest.mark.parametrize("schedule_type", ["http", "PYSCRIPT", "", None])
def test_invalid_schedule_type_rejected(schedule_type, client, jobs):
    request = dict(reference("flow")["equivalent_schedule_request"], schedule_action_type=schedule_type)

    assert_error(client.post(ENDPOINT, json=request), "schedule_action_type")
    assert jobs.count_documents({}) == 0


@pytest.mark.parametrize("body", ["not json", "[1, 2]", ""])
def test_non_object_body_rejected(body, client, jobs):
    response = client.post(ENDPOINT, content=body, headers={"content-type": "application/json"})

    assert_error(response)
    assert jobs.count_documents({}) == 0


def test_unknown_callback_rejected(client, jobs):
    request = dict(reference("pyscript")["equivalent_schedule_request"], schedule_action="missing_callback")

    assert_error(client.post(ENDPOINT, json=request), "missing_callback")
    assert jobs.count_documents({}) == 0


def test_empty_timezone_uses_local_zone(client, jobs):
    from tzlocal import get_localzone
    request = dict(reference("flow")["equivalent_schedule_request"], timezone="")

    assert client.post(ENDPOINT, json=request).json()["success"] is True
    job = pickle.loads(jobs.find_one({"_id": request["job_id"]})["job_state"])
    assert str(job["trigger"].run_date.tzinfo) == str(get_localzone())


def test_request_data_not_mutated_between_fields(client, jobs):
    """predefined_objects gets `event`; the slot data of a flow job is the request data verbatim."""
    request = reference("flow")["equivalent_schedule_request"]
    client.post(ENDPOINT, json=request)
    job = pickle.loads(jobs.find_one({"_id": request["job_id"]})["job_state"])
    assert json.loads(job["args"][2]["slot_data"]) == request["data"]


@mock.patch("apscheduler.schedulers.background.BackgroundScheduler.wakeup", autospec=True)
@mock.patch("apscheduler.schedulers.base.BaseScheduler._dispatch_event", autospec=True)
def test_dispatch_endpoint_still_works_for_endpoint_job(mock_dispatch_event, mock_wakeup, client, jobs):
    request = reference("pyscript")["equivalent_schedule_request"]
    client.post(ENDPOINT, json=request)

    response = client.get(f"/api/events/dispatch/{request['job_id']}")

    assert response.json() == {"data": None, "message": "Scheduled event dispatch!", "error_code": 0,
                               "success": True}
    event = mock_dispatch_event.call_args.args[1]
    assert event.job_id == request["job_id"]
    assert event.jobstore == JOB_STORE
    mock_wakeup.assert_called_once()
