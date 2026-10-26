import os

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

os.environ["system_file"] = "./tests/testing_data/system.yaml"

from kairon.shared.utils import Utility  # noqa: E402

Utility.load_environment()

from kairon.events.models import ScheduleActionRequest  # noqa: E402
from kairon.exceptions import AppException  # noqa: E402

REQUIRED_FIELDS = ["job_id", "run_at", "timezone", "schedule_action_type",
                   "schedule_action", "bot", "user", "data"]


def valid_payload(**overrides):
    payload = {
        "job_id": "0190f3a1b2c37d4e8f90a1b2c3d4e5f6",
        "run_at": "2030-01-15T10:30:00",
        "timezone": "Asia/Kolkata",
        "schedule_action_type": "pyscript",
        "schedule_action": "send_reminder",
        "bot": "6697add6b8e47524eb983374",
        "user": "default",
        "data": {"user": "1011"},
    }
    payload.update(overrides)
    return payload


def test_model_field_set_is_exact():
    assert list(ScheduleActionRequest.__fields__.keys()) == REQUIRED_FIELDS


@pytest.mark.parametrize("schedule_type", ["pyscript", "flow"])
def test_valid_request(schedule_type):
    req = ScheduleActionRequest.from_payload(valid_payload(schedule_action_type=schedule_type))
    assert req.schedule_action_type == schedule_type
    assert req.dict() == valid_payload(schedule_action_type=schedule_type)
    assert req.run_at_datetime.year == 2030


@pytest.mark.parametrize("run_at", ["2030-01-15T10:30:00", "2030-01-15T10:30:00Z",
                                    "2030-01-15T10:30:00+05:30", "2030-01-15T10:30:00.123456",
                                    "2030-01-15"])
def test_valid_run_at_formats(run_at):
    assert ScheduleActionRequest.from_payload(valid_payload(run_at=run_at)).run_at == run_at


@pytest.mark.parametrize("timezone", ["", "UTC", "Asia/Kolkata", "America/New_York"])
def test_valid_timezones(timezone):
    assert ScheduleActionRequest.from_payload(valid_payload(timezone=timezone)).timezone == timezone


def test_empty_data_allowed():
    assert ScheduleActionRequest.from_payload(valid_payload(data={})).data == {}


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_missing_field_rejected(field):
    payload = valid_payload()
    payload.pop(field)
    with pytest.raises(AppException, match=f"{field}: field required"):
        ScheduleActionRequest.from_payload(payload)


@pytest.mark.parametrize("schedule_type", ["http", "PYSCRIPT", "", "callback", None])
def test_invalid_schedule_type_rejected(schedule_type):
    with pytest.raises(AppException, match="schedule_action_type"):
        ScheduleActionRequest.from_payload(valid_payload(schedule_action_type=schedule_type))


@pytest.mark.parametrize("job_id", ["", "abc", "0190F3A1B2C37D4E8F90A1B2C3D4E5F6",
                                    "0190f3a1-b2c3-7d4e-8f90-a1b2c3d4e5f6",
                                    "0190f3a1b2c37d4e8f90a1b2c3d4e5f", "0190f3a1b2c37d4e8f90a1b2c3d4e5f6a",
                                    "zz90f3a1b2c37d4e8f90a1b2c3d4e5f6", 12345])
def test_invalid_job_id_rejected(job_id):
    with pytest.raises(AppException, match="job_id"):
        ScheduleActionRequest.from_payload(valid_payload(job_id=job_id))


@pytest.mark.parametrize("run_at", ["", "tomorrow", "15/01/2030 10:30", "2030-13-45T10:30:00", 1700000000])
def test_invalid_run_at_rejected(run_at):
    with pytest.raises(AppException, match="run_at"):
        ScheduleActionRequest.from_payload(valid_payload(run_at=run_at))


@pytest.mark.parametrize("timezone", ["Mars/Olympus", "IST+5", None])
def test_invalid_timezone_rejected(timezone):
    with pytest.raises(AppException, match="timezone"):
        ScheduleActionRequest.from_payload(valid_payload(timezone=timezone))


@pytest.mark.parametrize("field", ["schedule_action", "bot", "user"])
@pytest.mark.parametrize("value", ["", "   ", None])
def test_empty_string_fields_rejected(field, value):
    with pytest.raises(AppException, match=field):
        ScheduleActionRequest.from_payload(valid_payload(**{field: value}))


@pytest.mark.parametrize("data", [None, "a=b", ["x"]])
def test_invalid_data_rejected(data):
    with pytest.raises(AppException, match="data"):
        ScheduleActionRequest.from_payload(valid_payload(data=data))


def test_extra_field_rejected():
    with pytest.raises(AppException, match="cron_exp: extra field not permitted"):
        ScheduleActionRequest.from_payload(valid_payload(cron_exp="* * * * *"))


@pytest.mark.parametrize("payload", [None, [], "string"])
def test_non_object_body_rejected(payload):
    with pytest.raises(AppException, match="JSON object"):
        ScheduleActionRequest.from_payload(payload)


@pytest.fixture
def envelope_client():
    """
    App wired with the events server's own exception middleware, to prove model
    rejections surface as the server's HTTP 200 {success:false, error_code:422} envelope.
    The real route is added by the endpoint task; this probe route only parses the body.
    """
    from kairon.events.server import catch_exceptions_middleware

    probe = FastAPI()
    probe.middleware("http")(catch_exceptions_middleware)
    parsed = []

    @probe.post("/probe")
    async def probe_route(request: Request):
        req = ScheduleActionRequest.from_payload(await request.json())
        parsed.append(req)
        return {"success": True, "error_code": 0, "message": None, "data": {"job_id": req.job_id}}

    return TestClient(probe), parsed


def test_envelope_on_missing_field(envelope_client):
    client, parsed = envelope_client
    payload = valid_payload()
    payload.pop("bot")
    response = client.post("/probe", json=payload)
    assert response.status_code == 200
    assert response.json() == {"success": False, "error_code": 422, "message": "bot: field required", "data": None}
    assert parsed == []


def test_envelope_on_invalid_type(envelope_client):
    client, parsed = envelope_client
    response = client.post("/probe", json=valid_payload(schedule_action_type="http"))
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == 422
    assert body["message"] == "schedule_action_type: must be one of 'pyscript', 'flow'"
    assert parsed == []


def test_envelope_passes_valid(envelope_client):
    client, parsed = envelope_client
    response = client.post("/probe", json=valid_payload())
    assert response.status_code == 200
    assert response.json()["data"] == {"job_id": "0190f3a1b2c37d4e8f90a1b2c3d4e5f6"}
    assert len(parsed) == 1
