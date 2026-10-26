"""
Self-contained validation of the parity fixture recorder (tests/parity/recorder.py).

An inner pytest session (pytester) runs a miniature "action server" (FastAPI app that
calls requests + aiohttp upstreams and writes to a mongomock database) with the
recorder enabled, and the produced fixtures are checked against the schema.
"""
import json
import os
import textwrap

import pytest
from bson import json_util

from tests.parity import recorder

pytest_plugins = ["pytester"]

SCHEMA_PATH = os.path.join(os.path.dirname(recorder.__file__), "fixture-schema.json")

INNER_TESTS = textwrap.dedent('''
    import aiohttp
    import mongomock
    import pytest
    import requests
    import responses
    from aioresponses import aioresponses
    from bson import ObjectId
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient

    from tests.parity import recorder

    MONGO = mongomock.MongoClient()
    recorder.CLIENT_PROVIDER = lambda: MONGO
    recorder.DATABASES_PROVIDER = lambda client: ["kairon_test", "kairon_events"]
    DB = MONGO["kairon_test"]
    # present before any test body: one doc for the request bot, one unrelated
    DB["actions"].insert_one({"_id": ObjectId("65a000000000000000000001"), "bot": "bot_a", "name": "pre"})
    DB["actions"].insert_one({"_id": ObjectId("65a000000000000000000002"), "bot": "other", "name": "x"})

    app = FastAPI()

    @app.post("/webhook")
    async def webhook(request: Request):
        body = await request.json()
        bot = body["tracker"]["slots"]["bot"]
        r = requests.post("http://upstream.test/sync?q=1", json={"bot": bot},
                          headers={"X-Custom": "yes"})
        try:
            requests.get("http://upstream.test/unmatched")
            err = None
        except requests.exceptions.ConnectionError as e:
            err = "refused"
        async with aiohttp.ClientSession() as session:
            async with session.get("http://upstream.test/async", params={"p": "2"}) as resp:
                async_body = await resp.json()
        DB["action_server_logs"].insert_one({"_id": ObjectId("65a0000000000000000000ff"), "bot": bot,
                                             "status": "SUCCESS", "sync": r.json(), "async": async_body})
        DB["actions"].update_one({"name": "seeded"}, {"$set": {"used": True}})
        MONGO["kairon_events"]["jobs"].insert_one({"_id": "0" * 32, "next_run_time": 1.5})
        return {"events": [], "responses": [{"text": r.json()["msg"]}], "err": err}

    client = TestClient(app)

    def _post(bot="bot_a"):
        DB["actions"].insert_one({"_id": ObjectId("65a000000000000000000003"), "bot": "zz", "name": "seeded"})
        with responses.RequestsMock() as rsps, aioresponses() as aio:
            rsps.add(responses.POST, "http://upstream.test/sync?q=1", json={"msg": "hi"}, status=200)
            aio.get("http://upstream.test/async?p=2", payload={"a": 1}, status=201)
            return client.post("/webhook?x=1", json={"next_action": "act",
                                                      "tracker": {"slots": {"bot": bot}}})

    def _cleanup():
        DB["actions"].delete_one({"name": "seeded"})
        DB["action_server_logs"].delete_many({})
        MONGO["kairon_events"]["jobs"].delete_many({})

    def test_pass():
        try:
            response = _post()
            assert response.status_code == 200
            assert response.json()["responses"][0]["text"] == "hi"
            assert response.json()["err"] == "refused"
        finally:
            pass

    def test_fail():
        _cleanup()
        _post()
        assert False, "deliberate failure"

    @pytest.mark.skip(reason="skipped")
    def test_skipped():
        pass

    @pytest.mark.xfail(reason="xfail")
    def test_xfail():
        assert False

    @pytest.mark.parametrize("value", ["a/b c", "x::y"])
    def test_param(value):
        assert value

    def test_no_exchange():
        DB["action_server_logs"].insert_one({"_id": ObjectId("65a0000000000000000000ee"), "bot": "direct"})
''')

CLEANUP_FIXTURE = textwrap.dedent('''
    import pytest

    @pytest.fixture(autouse=True)
    def _isolate(request):
        yield
        import test_inner
        test_inner._cleanup()
        test_inner.DB["action_server_logs"].delete_many({})
''')


@pytest.fixture
def inner(pytester):
    pytester.makepyfile(test_inner=INNER_TESTS)
    pytester.makeconftest(CLEANUP_FIXTURE)
    yield pytester
    recorder.CLIENT_PROVIDER = None
    recorder.DATABASES_PROVIDER = None


def run_inner(pytester, out_dir, *extra):
    return pytester.runpytest_inprocess("-p", "tests.parity.recorder", "-p", "no:cacheprovider",
                                        "--record-fixtures-dir", str(out_dir), *extra)


def load(out_dir):
    return {f: json.loads((out_dir / f).read_text()) for f in sorted(os.listdir(out_dir))}


def node_file(out_dir, node_id):
    return out_dir / recorder.fixture_filename(node_id)


def test_disabled_by_default(inner):
    out_dir = inner.path / "fixtures"
    result = run_inner(inner, out_dir)
    result.assert_outcomes(passed=4, failed=1, skipped=1, xfailed=1)
    assert not out_dir.exists()


def test_records_only_passing_nodes(inner):
    out_dir = inner.path / "fixtures"
    out_dir.mkdir()
    stale = node_file(out_dir, "test_inner.py::test_fail")
    stale.write_text("{}")
    result = run_inner(inner, out_dir, "--record-fixtures")
    result.assert_outcomes(passed=4, failed=1, skipped=1, xfailed=1)
    fixtures = load(out_dir)
    assert sorted(f["node_id"] for f in fixtures.values()) == [
        "test_inner.py::test_no_exchange",
        "test_inner.py::test_param[a/b c]",
        "test_inner.py::test_param[x::y]",
        "test_inner.py::test_pass",
    ]
    for name, fixture in fixtures.items():
        assert name == recorder.fixture_filename(fixture["node_id"])
    assert not stale.exists()


def test_env_flag_enables(inner, monkeypatch):
    monkeypatch.setenv(recorder.ENV_FLAG, "1")
    out_dir = inner.path / "fixtures_env"
    run_inner(inner, out_dir)
    assert len(os.listdir(out_dir)) == 4


def test_fixture_content(inner):
    out_dir = inner.path / "fixtures"
    run_inner(inner, out_dir, "--record-fixtures", "-k", "test_pass")
    fixture = json.loads(node_file(out_dir, "test_inner.py::test_pass").read_text())

    assert fixture["schema_version"] == 1
    assert fixture["normalized"] is False

    # inbound exchange
    assert len(fixture["exchanges"]) == 1
    request = fixture["exchanges"][0]["request"]
    assert request["method"] == "POST" and request["path"] == "/webhook" and request["query"] == "x=1"
    assert request["body"] == {"encoding": "json",
                               "value": {"next_action": "act", "tracker": {"slots": {"bot": "bot_a"}}}}
    assert ["user-agent", "testclient"] in request["headers"]
    response = fixture["exchanges"][0]["response"]
    assert response["status"] == 200
    assert response["body"]["value"] == {"events": [], "responses": [{"text": "hi"}], "err": "refused"}

    # upstream calls with canned replies, in order
    upstream = fixture["upstream"]
    assert [u["seq"] for u in upstream] == [0, 1, 2]
    sync, unmatched, async_call = upstream
    assert sync["client"] == "requests"
    assert sync["request"]["method"] == "POST" and sync["request"]["url"] == "http://upstream.test/sync?q=1"
    assert sync["request"]["body"] == {"encoding": "json", "value": {"bot": "bot_a"}}
    assert ["X-Custom", "yes"] in sync["request"]["headers"]
    assert sync["response"]["status"] == 200
    assert sync["response"]["body"] == {"encoding": "json", "value": {"msg": "hi"}}
    assert sync["error"] is None
    assert unmatched["response"] is None
    assert unmatched["error"]["type"] == "requests.exceptions.ConnectionError"
    assert async_call["client"] == "aiohttp"
    assert async_call["request"]["method"] == "GET"
    assert async_call["request"]["url"] == "http://upstream.test/async?p=2"
    assert async_call["response"]["status"] == 201
    assert async_call["response"]["body"] == {"encoding": "json", "value": {"a": 1}}

    # mongo seed: bot-scoped pre-existing docs + docs created in the test before the request
    mongo = fixture["mongo"]
    assert mongo["available"] is True
    assert mongo["databases"] == ["kairon_test", "kairon_events"]
    seed_names = [d["name"] for d in mongo["seed"]["kairon_test"]["actions"]]
    assert seed_names == ["pre", "seeded"]
    assert mongo["seed"]["kairon_test"]["actions"][0]["_id"] == {"$oid": "65a000000000000000000001"}

    # mongo written: inserted / updated across both databases, canonical extended JSON
    logs = mongo["written"]["kairon_test"]["action_server_logs"]
    assert len(logs["inserted"]) == 1 and logs["updated"] == [] and logs["deleted"] == []
    assert logs["inserted"][0]["_id"] == {"$oid": "65a0000000000000000000ff"}
    assert logs["inserted"][0]["async"] == {"a": {"$numberInt": "1"}}
    updated = mongo["written"]["kairon_test"]["actions"]["updated"]
    assert [d["name"] for d in updated] == ["seeded"] and updated[0]["used"] is True
    job = mongo["written"]["kairon_events"]["jobs"]["inserted"][0]
    assert job == {"_id": "0" * 32, "next_run_time": {"$numberDouble": "1.5"}}
    decoded = json_util.loads(json.dumps(logs["inserted"][0]))
    assert str(decoded["_id"]) == "65a0000000000000000000ff"


def test_no_exchange_fixture(inner):
    out_dir = inner.path / "fixtures"
    run_inner(inner, out_dir, "--record-fixtures", "-k", "test_no_exchange")
    fixture = json.loads(node_file(out_dir, "test_inner.py::test_no_exchange").read_text())
    assert fixture["exchanges"] == [] and fixture["upstream"] == []
    assert fixture["mongo"]["seed"] == {}
    inserted = fixture["mongo"]["written"]["kairon_test"]["action_server_logs"]["inserted"]
    assert inserted == [{"_id": {"$oid": "65a0000000000000000000ee"}, "bot": "direct"}]


def test_all_fixtures_validate_against_schema(inner):
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(open(SCHEMA_PATH).read())
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    out_dir = inner.path / "fixtures"
    run_inner(inner, out_dir, "--record-fixtures")
    fixtures = load(out_dir)
    assert len(fixtures) == 4
    for name, fixture in fixtures.items():
        errors = list(validator.iter_errors(fixture))
        assert errors == [], (name, [e.message for e in errors])


def test_recording_is_repeatable_for_fixed_inputs(inner):
    first, second = inner.path / "run1", inner.path / "run2"
    run_inner(inner, first, "--record-fixtures")
    run_inner(inner, second, "--record-fixtures")
    assert sorted(os.listdir(first)) == sorted(os.listdir(second))
    for name in os.listdir(first):
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_recorder_restores_patches(inner):
    import responses as responses_lib
    from aioresponses import aioresponses
    from starlette.testclient import TestClient

    before = (TestClient.__dict__["request"], responses_lib.RequestsMock.__dict__["_on_request"],
              aioresponses.__dict__["match"])
    run_inner(inner, inner.path / "fixtures", "--record-fixtures")
    after = (TestClient.__dict__["request"], responses_lib.RequestsMock.__dict__["_on_request"],
             aioresponses.__dict__["match"])
    assert before == after


@pytest.mark.parametrize("raw, expected", [
    (None, {"encoding": "empty", "value": None}),
    (b"", {"encoding": "empty", "value": None}),
    (b'{"a": 1}', {"encoding": "json", "value": {"a": 1}}),
    ("plain", {"encoding": "text", "value": "plain"}),
    (b"\xff\xfe", {"encoding": "base64", "value": "//4="}),
    ({"k": "v"}, {"encoding": "form", "value": {"k": "v"}}),
])
def test_encode_body(raw, expected):
    assert recorder.encode_body(raw) == expected


def test_fixture_filename_is_stable_and_distinct():
    a = recorder.fixture_filename("tests/x.py::test[a/b]")
    b = recorder.fixture_filename("tests/x.py::test[a_b]")
    assert a == recorder.fixture_filename("tests/x.py::test[a/b]")
    assert a != b
    assert a.startswith("tests_x.py_test_a_b-") and a.endswith(".json")
