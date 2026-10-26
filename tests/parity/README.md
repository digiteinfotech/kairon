# Parity fixtures

This directory holds golden fixtures recorded from the Python action-server test suite. The Java port replays them to prove that its behaviour matches.

| File | Purpose |
|---|---|
| `recorder.py` | Pytest plugin that records one fixture per passing node. It is loaded by `tests/conftest.py` and does nothing unless enabled. |
| `normalize.py` | Placeholder normalization (used by the recorder) and the schema validation command. |
| `fixture-schema.md` | Field-by-field description of the fixture format, including volatile fields and placeholder tokens. |
| `fixture-schema.json` | JSON Schema (2020-12) that every fixture must validate against. |
| `fixtures/` | Output directory (one `*.json` file per node). |
| `capture_schedule_reference_jobs.py` | Regenerates the schedule_action reference job documents in `tests/testing_data/schedule_reference_jobs/`. |

## Recording

The recorder needs a MongoDB reachable at the `DATABASE_URL` from `tests/testing_data/system.yaml`, the same as the integration suite.

```bash
PYTHONPATH=$PWD .venv310/bin/pytest --record-fixtures \
    $(cat action-server/src/test/resources/python-action-nodes.txt)
# or: KAIRON_RECORD_FIXTURES=1 .venv310/bin/pytest tests/integration_test/action_service_test.py
```

| Option / env | Effect |
|---|---|
| `--record-fixtures` / `KAIRON_RECORD_FIXTURES=1` | Enables recording. |
| `--record-fixtures-dir DIR` / `KAIRON_RECORD_DIR` | Sets the output directory (default `tests/parity/fixtures`). |
| `KAIRON_RECORD_DATABASES=db1,db2` | Sets the databases to snapshot. The default is the mongoengine default DB plus `events.queue.name`. |

Recording behaviour:

- No test file is edited. The plugin patches `starlette.testclient.TestClient.request`, `responses.RequestsMock._on_request` and `aioresponses.match` only while a test body runs.
- A node gets a fixture only when its setup, call and teardown all pass. Failed, skipped and xfail/xpass nodes get none, and any stale fixture for them is deleted.
- Fixtures are normalized (`normalized: true`): run-time timestamps, ObjectIds, UUIDs, JWTs and request ids are replaced by placeholder tokens (`normalize.py`, rules in `fixture-schema.md`), so two recordings are byte-identical. `--record-raw` / `KAIRON_RECORD_RAW=1` writes raw values instead.

## Validating

```bash
PYTHONPATH=$PWD .venv310/bin/python -m tests.parity.normalize --validate tests/parity/fixtures
```

It prints each schema violation and exits with status 1 if any fixture is invalid. Without `--validate`, raw fixtures are first normalized in place.
- Mongo snapshots read every document in the snapshotted databases three times per node. Use this for recording only, not for everyday runs.

## Limits

- Outbound calls stubbed with `unittest.mock.patch`, `pytest_httpx` or monkeypatching are not captured. Such nodes need to be triaged as untranslatable.
- If an aiohttp consumer reads `resp.content` (the raw stream) directly, it sees an exhausted stream, because the recorder reads the canned body first. `resp.read()`, `resp.json()` and `resp.text()` work.
