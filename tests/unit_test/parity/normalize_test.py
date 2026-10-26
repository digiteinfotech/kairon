"""
Placeholder normalization and schema validation of parity fixtures (tests/parity/normalize.py).
"""
import base64
import json
import os
import textwrap
import time

import pytest

from tests.parity import normalize, recorder

pytest_plugins = ["pytester"]

NOW = 1790000000.0  # fixed reference time (2026-09)
OID_NOW = "%08x" % int(NOW) + "0000000000000001"           # minted "now"
OID_NOW_2 = "%08x" % int(NOW) + "0000000000000002"
OID_FIXED = "6697add6b8e47524eb983374"                       # hard-coded test bot id (2024)
UUID7_HEX = "%012x" % int(NOW * 1000) + "7abc8def0123456789ab"
UUID4 = "1b4e28ba-2fa1-4d3b-a3f5-ef19b5a7bd51"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJl"
REQUEST_ID = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"


def raw_fixture(oid_now=OID_NOW, oid_now_2=OID_NOW_2, uuid7_hex=UUID7_HEX, uuid4=UUID4,
                request_id=REQUEST_ID):
    OID_NOW, OID_NOW_2, UUID7_HEX, UUID4, REQUEST_ID = oid_now, oid_now_2, uuid7_hex, uuid4, request_id  # noqa: N806
    return {
        "schema_version": 1,
        "node_id": "tests/x.py::test_a",
        "normalized": False,
        "mongo": {
            "available": True,
            "databases": ["kairon", "kairon_events"],
            "seed": {"kairon": {"actions": [
                {"_id": {"$oid": OID_NOW_2}, "bot": OID_FIXED, "name": "b"},
                {"_id": {"$oid": OID_NOW}, "bot": OID_FIXED, "name": "a",
                 "created_on": {"$date": {"$numberLong": str(int(NOW * 1000))}},
                 "fixed_on": {"$date": {"$numberLong": "1500000000000"}}},
            ]}},
            "written": {
                "kairon": {"action_server_logs": {"inserted": [
                    {"_id": {"$oid": OID_NOW_2}, "request_id": REQUEST_ID, "ref": OID_NOW,
                     "timestamp": {"$date": {"$numberLong": str(int(NOW * 1000) + 5)}},
                     "elapsed": {"$numberDouble": "0.25"}, "phone": "9876543210"},
                ], "updated": [], "deleted": []}},
                "kairon_events": {"kscheduler": {"inserted": [
                    {"_id": UUID7_HEX, "next_run_time": {"$numberDouble": str(NOW + 60)},
                     "job_state": {"$binary": {"base64": base64.b64encode(
                         b"\x80\x05pickle" + UUID7_HEX.encode() + b"\x00").decode(), "subType": "00"}}},
                    {"_id": "0" * 32, "next_run_time": {"$numberDouble": "1.5"},
                     "job_state": {"$binary": {"base64": base64.b64encode(b"static").decode(), "subType": "00"}}},
                ], "updated": [], "deleted": []}},
            },
        },
        "exchanges": [{
            "request": {"method": "POST", "path": "/webhook", "query": "",
                        "headers": [["content-type", "application/json"]],
                        "body": {"encoding": "json", "value": {"sender_id": UUID4, "bot": OID_FIXED}}},
            "response": {"status": 200, "headers": [["X-Request-ID", REQUEST_ID]],
                         "body": {"encoding": "json", "value": {"events": [
                             {"event": "slot", "value": "2026-09-21T14:13:20.123456+00:00"},
                             {"event": "slot", "value": "2019-01-01T00:00:00"}]}}},
        }],
        "upstream": [{
            "seq": 0, "client": "aiohttp",
            "request": {"method": "GET", "url": f"http://events/api/events/dispatch/{UUID7_HEX}",
                        "headers": [["Authorization", f"Bearer {JWT}"], ["X-TIMESTAMP", str(int(NOW))],
                                    ["X-Kairon-Request-ID", REQUEST_ID]],
                        "body": {"encoding": "json", "value": {"ts": int(NOW * 1000), "count": 3,
                                                               "id": UUID4, "obj": OID_NOW}}},
            "response": {"status": 200, "headers": [], "body": {"encoding": "empty", "value": None}},
            "error": None,
        }],
    }


@pytest.fixture
def normalized():
    return normalize.normalize_fixture(raw_fixture(), reference_time=NOW)


def test_flag_and_identity_fields(normalized):
    assert normalized["normalized"] is True
    assert normalized["schema_version"] == 1
    assert normalized["node_id"] == "tests/x.py::test_a"
    assert list(normalized.keys()) == list(raw_fixture().keys())


def test_object_ids_indexed_consistently(normalized):
    seed = normalized["mongo"]["seed"]["kairon"]["actions"]
    # documents re-ordered by masked content: "a" before "b"
    assert [d["name"] for d in seed] == ["a", "b"]
    assert seed[0]["_id"] == "{{OBJECT_ID:1}}"
    assert seed[1]["_id"] == "{{OBJECT_ID:2}}"
    log = normalized["mongo"]["written"]["kairon"]["action_server_logs"]["inserted"][0]
    assert log["_id"] == "{{OBJECT_ID:2}}"      # same ObjectId -> same index
    assert log["ref"] == "{{OBJECT_ID:1}}"      # 24-hex string form shares the $oid index
    assert normalized["upstream"][0]["request"]["body"]["value"]["obj"] == "{{OBJECT_ID:1}}"


def test_fixed_values_kept(normalized):
    seed = normalized["mongo"]["seed"]["kairon"]["actions"]
    assert seed[0]["bot"] == OID_FIXED
    assert seed[0]["fixed_on"] == {"$date": {"$numberLong": "1500000000000"}}
    log = normalized["mongo"]["written"]["kairon"]["action_server_logs"]["inserted"][0]
    assert log["elapsed"] == {"$numberDouble": "0.25"}
    assert log["phone"] == "9876543210"
    static_job = normalized["mongo"]["written"]["kairon_events"]["kscheduler"]["inserted"][0]
    assert static_job["_id"] == "0" * 32
    assert static_job["next_run_time"] == {"$numberDouble": "1.5"}
    assert static_job["job_state"]["$binary"]["base64"] == base64.b64encode(b"static").decode()
    events = normalized["exchanges"][0]["response"]["body"]["value"]["events"]
    assert events[1]["value"] == "2019-01-01T00:00:00"
    assert normalized["upstream"][0]["request"]["body"]["value"]["count"] == 3


def test_timestamps_and_epochs(normalized):
    seed = normalized["mongo"]["seed"]["kairon"]["actions"]
    assert seed[0]["created_on"] == "{{TIMESTAMP}}"
    log = normalized["mongo"]["written"]["kairon"]["action_server_logs"]["inserted"][0]
    assert log["timestamp"] == "{{TIMESTAMP}}"
    job = normalized["mongo"]["written"]["kairon_events"]["kscheduler"]["inserted"][1]
    assert job["next_run_time"] == "{{EPOCH}}"
    events = normalized["exchanges"][0]["response"]["body"]["value"]["events"]
    assert events[0]["value"] == "{{DATETIME}}"
    upstream = normalized["upstream"][0]["request"]
    assert ["X-TIMESTAMP", "{{EPOCH}}"] in upstream["headers"]
    assert upstream["body"]["value"]["ts"] == "{{EPOCH}}"


def test_uuids_jwt_request_ids_and_binary(normalized):
    # documents are ordered by masked content: "000..." sorts before "{{UUID_HEX}}"
    static_job, job = normalized["mongo"]["written"]["kairon_events"]["kscheduler"]["inserted"]
    assert static_job["_id"] == "0" * 32
    assert job["_id"] == "{{UUID_HEX:1}}"
    assert job["job_state"]["$binary"] == {"base64": "{{BINARY}}", "subType": "00"}
    upstream = normalized["upstream"][0]["request"]
    assert upstream["url"] == "http://events/api/events/dispatch/{{UUID_HEX:1}}"
    assert ["Authorization", "Bearer {{JWT}}"] in upstream["headers"]
    assert ["X-Kairon-Request-ID", "{{REQUEST_ID}}"] in upstream["headers"]
    assert upstream["body"]["value"]["id"] == "{{UUID:1}}"
    exchange = normalized["exchanges"][0]
    assert exchange["request"]["body"]["value"]["sender_id"] == "{{UUID:1}}"
    assert exchange["response"]["headers"] == [["X-Request-ID", "{{REQUEST_ID}}"]]
    log = normalized["mongo"]["written"]["kairon"]["action_server_logs"]["inserted"][0]
    assert log["request_id"] == "{{REQUEST_ID}}"


def test_no_volatile_value_survives(normalized):
    text = json.dumps(normalized)
    for value in (OID_NOW, OID_NOW_2, UUID7_HEX, UUID4, JWT, REQUEST_ID, str(int(NOW))):
        assert value not in text


def test_deterministic_across_raw_id_order_and_values():
    """Two recordings differing only in volatile values and raw document order normalize identically."""
    first = raw_fixture()
    second = raw_fixture(oid_now="%08x" % int(NOW + 7) + "00000000000000aa",
                         oid_now_2="%08x" % int(NOW + 7) + "00000000000000bb",
                         uuid7_hex="%012x" % int((NOW + 7) * 1000) + "7fff8def0123456789ab",
                         uuid4="9a8b7c6d-1111-4222-9333-444455556666",
                         request_id="ffeeddccbbaa99887766554433221100")
    second["mongo"]["seed"]["kairon"]["actions"].reverse()
    out1 = recorder.dump_fixture(normalize.normalize_fixture(first, reference_time=NOW))
    out2 = recorder.dump_fixture(normalize.normalize_fixture(second, reference_time=NOW + 30))
    assert out1 == out2


def test_normalizing_twice_is_stable(normalized):
    assert normalize.normalize_fixture(normalized, reference_time=NOW) == normalized


def test_normalized_fixture_validates(normalized):
    assert normalize.validate_fixture(normalized) == []
    assert normalize.validate_fixture(raw_fixture()) == []


@pytest.mark.parametrize("mutate, fragment", [
    (lambda f: f.pop("node_id"), "'node_id' is a required property"),
    (lambda f: f.update(schema_version=2), "/schema_version"),
    (lambda f: f.update(extra=1), "Additional properties"),
    (lambda f: f["upstream"][0].update(client="httpx"), "/upstream/0/client"),
    (lambda f: f["exchanges"][0]["response"].update(status=99), "/exchanges/0/response/status"),
])
def test_validation_rejects_schema_violations(mutate, fragment, normalized):
    mutate(normalized)
    errors = normalize.validate_fixture(normalized)
    assert errors and any(fragment in e for e in errors), errors


def test_cli_validate_rejects_invalid_fixture(tmp_path, normalized, capsys):
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(recorder.dump_fixture(normalized))
    broken = dict(normalized)
    broken.pop("mongo")
    bad.write_text(recorder.dump_fixture(broken))

    assert normalize.main(["--validate", str(good)]) == 0
    assert normalize.main(["--validate", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert f"INVALID {bad}" in out and "'mongo' is a required property" in out
    assert "1/2 fixtures valid" in out
    assert good.read_text() == recorder.dump_fixture(normalized)


def test_cli_normalizes_raw_files_in_place(tmp_path):
    path = tmp_path / "raw.json"
    path.write_text(recorder.dump_fixture(raw_fixture()))
    os.utime(path, (NOW, NOW))

    assert normalize.main([str(path)]) == 0
    assert path.read_text() == recorder.dump_fixture(normalize.normalize_fixture(raw_fixture(), NOW))


# ----------------------------------------------------------------- end to end via the recorder

INNER = textwrap.dedent('''
    import datetime
    import re
    import uuid

    import mongomock
    import pytest
    import responses
    import requests
    from bson import ObjectId
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient
    from uuid6 import uuid7

    from tests.parity import recorder

    MONGO = mongomock.MongoClient()
    recorder.CLIENT_PROVIDER = lambda: MONGO
    recorder.DATABASES_PROVIDER = lambda client: ["kairon_test", "kairon_events"]
    DB = MONGO["kairon_test"]
    app = FastAPI()

    @app.post("/webhook")
    async def webhook(request: Request):
        body = await request.json()
        request_id = uuid.uuid4().hex
        job_id = uuid7().hex
        now = datetime.datetime.utcnow()
        requests.get(f"http://events.test/api/events/dispatch/{job_id}",
                     headers={"X-TIMESTAMP": str(int(now.timestamp())), "X-Kairon-Request-ID": request_id})
        MONGO["kairon_events"]["kscheduler"].insert_one({"_id": job_id, "next_run_time": now.timestamp() + 60})
        DB["action_server_logs"].insert_one({"bot": body["bot"], "timestamp": now, "request_id": request_id,
                                             "sender": str(uuid.uuid4())})
        return JSONResponse({"time": now.isoformat(), "job": job_id}, headers={"X-Request-ID": request_id})

    client = TestClient(app)

    def test_volatile():
        DB["actions"].insert_one({"_id": ObjectId(), "bot": "6697add6b8e47524eb983374", "name": "seeded"})
        with responses.RequestsMock() as rsps:
            rsps.add(responses.GET, re.compile(r"http://events\\.test/.*"), json={"success": True})
            assert client.post("/webhook", json={"bot": "6697add6b8e47524eb983374"}).status_code == 200

    @pytest.fixture(autouse=True)
    def _cleanup():
        yield
        DB["actions"].delete_many({})
        DB["action_server_logs"].delete_many({})
        MONGO["kairon_events"]["kscheduler"].delete_many({})
''')


@pytest.fixture
def volatile_inner(pytester):
    pytester.makepyfile(test_volatile=INNER)
    yield pytester
    recorder.CLIENT_PROVIDER = None
    recorder.DATABASES_PROVIDER = None


def run(pytester, out_dir, *extra):
    result = pytester.runpytest_inprocess("-p", "tests.parity.recorder", "-p", "no:cacheprovider",
                                          "--record-fixtures", "--record-fixtures-dir", str(out_dir), *extra)
    result.assert_outcomes(passed=1)
    files = os.listdir(out_dir)
    assert len(files) == 1
    return (out_dir / files[0]).read_bytes()


def test_recording_twice_is_byte_identical(volatile_inner):
    first = run(volatile_inner, volatile_inner.path / "run1")
    time.sleep(1.1)  # different second -> different timestamps/epochs in the raw values
    second = run(volatile_inner, volatile_inner.path / "run2")
    assert first == second

    fixture = json.loads(first)
    assert fixture["normalized"] is True
    assert normalize.validate_fixture(fixture) == []
    job = fixture["mongo"]["written"]["kairon_events"]["kscheduler"]["inserted"][0]
    assert job == {"_id": "{{UUID_HEX:1}}", "next_run_time": "{{EPOCH}}"}
    assert fixture["upstream"][0]["request"]["url"] == "http://events.test/api/events/dispatch/{{UUID_HEX:1}}"
    log = fixture["mongo"]["written"]["kairon_test"]["action_server_logs"]["inserted"][0]
    assert log["_id"] == "{{OBJECT_ID:2}}" and log["timestamp"] == "{{TIMESTAMP}}"
    assert log["request_id"] == "{{REQUEST_ID}}" and log["sender"] == "{{UUID:1}}"
    assert log["bot"] == "6697add6b8e47524eb983374"
    assert fixture["mongo"]["seed"]["kairon_test"]["actions"][0]["_id"] == "{{OBJECT_ID:1}}"
    response = fixture["exchanges"][0]["response"]
    assert ["x-request-id", "{{REQUEST_ID}}"] in response["headers"]
    assert response["body"]["value"] == {"time": "{{DATETIME}}", "job": "{{UUID_HEX:1}}"}


def test_record_raw_keeps_values(volatile_inner):
    raw = json.loads(run(volatile_inner, volatile_inner.path / "raw", "--record-raw"))
    assert raw["normalized"] is False
    assert "{{" not in json.dumps(raw)
    assert normalize.validate_fixture(raw) == []
