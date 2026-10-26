# Parity fixture schema, version 1

A parity fixture records one passing pytest node from the Python action-server suite. The port's replay harness uses it to run the same scenario against the new server and compare results. The machine-readable form of this schema is `fixture-schema.json` (JSON Schema 2020-12). Every recorded fixture must validate against it.

The recorder is `tests/parity/recorder.py`, and its usage is described in `README.md`.

## Encoding rules

- Each fixture is a UTF-8 JSON file named `<slug(node_id)>-<sha1(node_id)[:10]>.json`. The slug replaces every run of characters outside `[A-Za-z0-9._-]` with `_` and is cut to 150 characters.
- MongoDB documents and `_id` values are written as **canonical extended JSON**: `bson.json_util` with `CANONICAL_JSON_OPTIONS`. Examples are `{"$oid": ...}`, `{"$date": {"$numberLong": ...}}`, `{"$numberInt": "1"}`, `{"$numberDouble": "1.5"}` and `{"$binary": {"base64": ..., "subType": "00"}}`. Decode them with `bson.json_util.loads` or an equivalent extended-JSON reader to get the BSON types back.
- HTTP bodies are **not** extended JSON. They are plain JSON values inside a body envelope.
- Document field order is the order in which MongoDB returned the fields, and the recorder keeps it as is.
- Fixture keys are written in the order shown in this document.

## Top level

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | integer, always `1` | Version of this schema. Any incompatible change bumps it. |
| `node_id` | string | The pytest node id, e.g. `tests/integration_test/action_service_test.py::test_http_action_execution`. |
| `normalized` | boolean | `false` for a raw recording. `true` after the normalization pass (T-041) has replaced volatile values with placeholder tokens. |
| `mongo` | object | Database state. See below. |
| `exchanges` | array | Inbound requests sent through starlette's `TestClient`, with their responses, in call order. Normally there is a single `POST /webhook`. The array is empty for tests that call action classes directly. |
| `upstream` | array | Outbound HTTP calls answered by a `responses` or `aioresponses` mock, in call order. |

## `mongo`

| Field | Type | Meaning |
|---|---|---|
| `available` | boolean | `false` when no Mongo connection was reachable during recording. `seed` and `written` are then empty. |
| `databases` | string[] | The databases that were snapshotted. By default this is the mongoengine default DB plus the events queue DB (`events.queue.name`). Override it with `KAIRON_RECORD_DATABASES`. |
| `seed` | `{db: {collection: [document]}}` | Documents present at the moment the **first** inbound request was sent. A document is included if (a) it was created or changed after the test body started, or (b) its `bot` field equals the bot of that request (`tracker.slots.bot` or top-level `bot`). Replay inserts these before posting the request. Documents in each collection are sorted by canonical `_id`. The map is empty when there is no exchange. |
| `written` | `{db: {collection: {inserted, updated, deleted}}}` | Differences between the snapshot taken at the first inbound request and the snapshot taken at the end of the test body. With no exchange, the baseline is the start of the test body. `inserted` and `updated` hold full documents (for `updated`, the version after the change). `deleted` holds the `_id` values that were removed. |

## Body envelope

`{"encoding": E, "value": V}`

| `encoding` | `value` |
|---|---|
| `empty` | `null` (no body) |
| `json` | The parsed JSON value. This is used whenever the body parses as JSON. |
| `text` | The UTF-8 text, for bodies that are not JSON. |
| `form` | An object, for an aiohttp `data=` dict (form fields). |
| `base64` | Base64 of the raw bytes, for bodies that are not UTF-8. |

## Headers

Headers are arrays of `[name, value]` pairs in send order. Duplicates are kept. Name casing is kept as the client produced it.

## `exchanges[]`

| Field | Meaning |
|---|---|
| `request.method` | HTTP method, as sent. |
| `request.path` | URL path, e.g. `/webhook`. |
| `request.query` | Raw query string, or `""` if there is none. |
| `request.headers` | All headers the TestClient sent, including `host`, `user-agent: testclient`, `content-type` and `content-length`. |
| `request.body` | Body envelope of the bytes actually sent. |
| `response.status` | HTTP status code. |
| `response.headers` | All response headers. |
| `response.body` | Body envelope. |

## `upstream[]`

| Field | Meaning |
|---|---|
| `seq` | 0-based call order within the node. |
| `client` | `requests` (answered by the `responses` library) or `aiohttp` (answered by `aioresponses`). |
| `request.method` | Upper-case method. |
| `request.url` | Full URL. For aiohttp, `params` are already merged into the query string. |
| `request.headers` | The headers passed by the caller. For aiohttp these are only the explicitly passed headers. |
| `request.body` | Body envelope. For aiohttp `json=` the encoding is `json`. A `data=` dict becomes `form`, and bytes or text go through the usual detection. |
| `response` | The canned reply (`status`, `headers`, `body`). It is `null` when the mock raised an error or had no match. |
| `error` | `null`, or `{type, message}` when the mock raised (for example `requests.exceptions.ConnectionError`, an `aiohttp` exception registered with `exception=`) or found no match (`aiohttp.ClientConnectionError`). |

Calls mocked by other means are **not** captured. That covers `unittest.mock.patch` on functions, `pytest_httpx` and monkeypatched clients. Replay reports such nodes as untranslatable (parity-harness R5).

## Volatile fields

Raw (`normalized: false`) recordings contain values that change from run to run. The normalization pass (T-041) replaces them with the tokens below. Until it runs, two recordings of the same suite are not byte-identical.

| Where | Volatile values |
|---|---|
| Mongo documents | `_id` (ObjectId, or a uuid7 hex string for scheduler jobs); `timestamp`, `start_timestamp`, `end_timestamp`, `created_on`, `updated_on` and `user_timestamp` dates; `request_id`; `next_run_time` (epoch float) in scheduler jobs; `job_state` pickle bytes (they embed the job id) |
| Inbound response | `X-Request-ID` header, `date`/`server`-type headers, and any time-based slot values echoed in `events` |
| Upstream request | `X-TIMESTAMP`/`timestamp` headers, `Authorization: Bearer <JWT>` (callback and kairon tokens), uuid/uuid7 ids in URLs and bodies (callback ids, schedule job ids, `/api/events/dispatch/{id}`) |
| Bodies (any) | ISO-8601 date-times, epoch seconds/milliseconds near "now", ObjectId hex strings minted during the test, JWTs |

## Placeholder tokens

Placeholders appear only when `normalized` is `true`. Each token is a whole JSON string value. Inside a URL or a header value, the token replaces just the matching substring. When a token carries an index `:n`, the same original value maps to the same index everywhere in that fixture. This lets replay check that values are consistent, for example that the id written to Mongo matches the id in the dispatch URL.

| Token | Replaces |
|---|---|
| `{{TIMESTAMP}}` | A BSON date (`{"$date": ...}`) recorded at run time |
| `{{DATETIME}}` | An ISO-8601 date-time string generated at run time |
| `{{EPOCH}}` | An epoch-seconds or epoch-milliseconds number or string generated at run time |
| `{{OBJECT_ID:n}}` | An ObjectId (`{"$oid": ...}` or 24-hex string) minted during the test |
| `{{UUID:n}}` | A dashed UUID string |
| `{{UUID_HEX:n}}` | A 32-hex UUID string (uuid4 or uuid7 `.hex`, e.g. schedule job ids) |
| `{{JWT}}` | A JSON Web Token (`xxx.yyy.zzz` base64url) |
| `{{REQUEST_ID}}` | The request id generated by the server for this exchange |

Fixed ids written by the test itself (such as hard-coded bot ids) are not volatile and are kept verbatim.

## Versioning

Additive optional fields do not bump `schema_version`. Removing or renaming a field, or changing its meaning, bumps it, and replay must refuse versions it does not know.
