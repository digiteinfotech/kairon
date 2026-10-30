---
created: "2026-10-26T12:44:00Z"
last_edited: "2026-10-30"
---

# Cavekit: Webhook Contract

## Scope
The HTTP surface that Rasa calls on the new action server: request parsing, the tracker model, the response envelope, the error contract, middleware headers and health endpoints. The port must be a drop-in replacement for the existing Python action server on this surface. No action logic, logging or templating lives here.

See context/refs/research-brief-java-action-server-port.md for evidence.

## Requirements

### R1: Request acceptance
**Description:** `POST /webhook` accepts a JSON object with keys `next_action`, `tracker`, `domain`, `version` and optional `trigger_info`. Unknown keys are ignored. Tracker fields default exactly as the reference Rasa SDK tracker parsing does.
**Acceptance Criteria:**
- [ ] A request containing an extra top-level key not in the list above returns the same response as the same request without that key
- [ ] A tracker missing `slots` is treated as `slots` = `{}`
- [ ] A tracker missing `latest_message` is treated as `{}`
- [ ] A tracker missing `events` is treated as `[]`
- [x] A tracker missing `paused` is treated as `false` (verified: TrackerStateTest#defaultsMatchRasaSdk)
- [ ] A tracker missing `followup_action` is treated as `null`
- [x] A tracker without `active_loop` but with `active_form` uses the `active_form` value as the active loop (verified: TrackerStateTest#activeFormIsTheFallbackActiveLoop)
- [x] A tracker without both `active_loop` and `active_form` uses `{}` as the active loop (verified: TrackerStateTest#defaultsMatchRasaSdk)
- [x] A tracker missing `latest_action_name` is treated as `null` (verified: TrackerStateTest#defaultsMatchRasaSdk)
- [x] A tracker missing `stack` is treated as `[]` (verified: TrackerStateTest#defaultsMatchRasaSdk)
- [x] A tracker without `sender_id` returns HTTP 500 and executes no action (same path as a missing tracker, R3) (verified: WebhookTest#missingSenderIdIs500)
- [ ] A missing `domain` is treated as `{}`
- [ ] A `version` value different from the server's pinned Rasa SDK version produces a log line and does not change the response
**Dependencies:** none

### R2: Response envelope
**Description:** A successful dispatch returns `{"events":[...],"responses":[...]}`. Events are slot events only. Each response message carries all 8 Rasa SDK message keys.
**Acceptance Criteria:**
- [ ] Every event has exactly the shape `{"event":"slot","timestamp":null,"name":<key>,"value":<value>}`
- [ ] One slot event is emitted per key returned by the action, in the action's insertion order
- [ ] A returned slot whose value is `null` still produces a slot event with `"value":null`
- [ ] No event with an `event` value other than `slot` is ever emitted
- [ ] Every response message contains the keys `text`, `buttons`, `elements`, `custom`, `template`, `response`, `image`, `attachment` in that order
- [ ] Unset message keys default to `text:null`, `buttons:[]`, `elements:[]`, `custom:{}`, `template:null`, `response:null`, `image:null`, `attachment:null`
- [ ] Extra message keyword fields an action supplies appear as additional top-level keys of that message
- [ ] An utterance with no text still appends a message whose `text` is `null`
- [ ] [UNVERIFIED] Response JSON for each recorded fixture equals the recorded Python response after normalization (see cavekit-parity-harness.md R3)
**Dependencies:** none

### R3: Error contract
**Description:** Error handling matches the existing Python server exactly. Existing port tests that expect HTTP 422 are wrong and must be corrected to this contract.
**Acceptance Criteria:**
- [ ] `next_action` that is missing, empty or whitespace-only returns HTTP 200 with body `null`
- [x] A body that is a JSON object without a `tracker` key (and with a non-blank `next_action`) returns HTTP 500 (verified: WebhookTest#missingTrackerIs500)
- [x] A body that is not a JSON object, or is empty, returns HTTP 200 with body `{"success":false,"error_code":422,"message":[...],"data":null}` where `message` is a list (verified: WebhookTest#emptyBodyIsErrorEnvelope, WebhookTest#nonObjectBodyIsErrorEnvelope)
- [ ] Any failure raised while executing an action returns HTTP 200 with `events: []` and `responses` = the messages uttered before the failure (`[]` when nothing was uttered)
- [x] No request to `/webhook` returns HTTP 422 as the status code (verified: WebhookTest#noRequestReturns422Status)
**Dependencies:** none

### R4: Middleware headers
**Description:** Every response carries the same CORS, compression, request-id and secure headers the Python server emits.
**Acceptance Criteria:**
- [ ] A request with header `X-Kairon-Request-ID: abc` gets a response with `X-Kairon-Request-ID: abc`
- [x] A request without `X-Kairon-Request-ID` gets a response with an `X-Kairon-Request-ID` value that is a valid UUID version 4 (verified: RequestIdAndGzipTest#missingRequestIdIsGeneratedAsUuid4)
- [x] `Access-Control-Allow-Origin` equals the request `Origin` header when present, else the first configured allowed origin (verified: CorsTest#allowedOriginIsEchoedWithCredentials, CorsTest#noOriginGetsFirstConfiguredOrigin)
- [x] CORS allows credentials, all methods and all headers (verified: CorsTest#preflightAllowsAllMethodsAndRequestedHeaders)
- [ ] [UNVERIFIED] A request with `Accept-Encoding: gzip` and a response body larger than 1 KB returns `Content-Encoding: gzip`
- [x] Responses carry `Strict-Transport-Security`, `Content-Security-Policy`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `Cache-Control` containing `must-revalidate`, `X-Content-Type-Options`, `Server: Secure`, `Cross-Origin-Embedder-Policy: require-corp`, `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Resource-Policy: same-origin` (verified: WebhookTest#secureHeadersMatchPython)
- [ ] [GAP] Each secure-header value equals the value captured from the Python server for the same request
**Dependencies:** cavekit-config-and-deploy.md R1

### R5: Health endpoints and auth
**Description:** The two health endpoints return fixed bodies. No endpoint requires authentication.
**Acceptance Criteria:**
- [ ] `GET /` returns HTTP 200 with body `{"message":"Kairon Action Server Up and Running"}`
- [ ] `GET /healthcheck` returns HTTP 200 with body `{"message":"health check ok"}`
- [ ] `POST /webhook` without an `Authorization` header is processed normally
**Dependencies:** none

### R6: Request size
**Description:** The server accepts request bodies at least as large as the Python server accepts in practice. The Python server imposes no body-size limit.
**Acceptance Criteria:**
- [x] A valid webhook request with a 20 MB tracker is processed and does not return HTTP 413 (verified: RequestSizeTest#twentyMegabyteTrackerIsProcessed)
- [ ] [UNVERIFIED] The configured body-size ceiling is documented and agreed (needs human review)
**Dependencies:** cavekit-config-and-deploy.md R1

## Out of Scope
- Action behaviour, action-type resolution and logging (cavekit-dispatch-and-logging.md, cavekit-core-actions.md, cavekit-integration-actions.md, cavekit-orchestration-actions.md)
- Templating and parameter resolution (cavekit-templating-and-secrets.md)
- `domain_digest` handling (Rasa SDK >= 3.9) beyond ignoring unknown keys
- prompt_action and database_action behaviour (cavekit-prompt-database-actions.md); they use this envelope unchanged
- Lambda transports, LLM rephrase in kairon_bot_response, native image
- Authentication of any endpoint

## Cross-References
- See also: cavekit-templating-and-secrets.md
- See also: cavekit-dispatch-and-logging.md
- See also: cavekit-core-actions.md
- See also: cavekit-integration-actions.md
- See also: cavekit-orchestration-actions.md
- See also: cavekit-parity-harness.md
- See also: cavekit-config-and-deploy.md

## Source Traceability
- R1: kairon/actions/server.py:315-333; rasa_sdk/interfaces.py:24-36 (Tracker.from_dict)
- R2: rasa_sdk/executor.py:34-66, 377-381; rasa_sdk/events.py:44-47; kairon/actions/handlers/processor.py:17-48
- R3: kairon/actions/server.py:162-262 (185-192 validation envelope); kairon/actions/handlers/action.py:11-35 (line 19 KeyError on tracker)
- R4: kairon/shared/middleware.py; kairon/actions/server.py middleware setup
- R5: kairon/actions/server.py health routes
- R6: docker/docker-compose.yml:77-95 (uvicorn launch, no body limit)

## Gap Summary
Brownfield verification against the existing port (2026-10-26): 21 met, 15 gaps, 3 unverified by code reading.
Criteria prefixed `[GAP]` are not satisfied by the current code; `[UNVERIFIED]` need runtime, fixture, or human confirmation.

| Req | Gap | Evidence |
|---|---|---|
| R1 | A tracker missing `latest_action_name` is treated as `null` | action-server/src/main/java/com/kairon/action/runtime/TrackerState.java:31-41 — latest_action_name is not modelled. |
| R1 | A tracker missing `paused` is treated as `false` | action-server/src/main/java/com/kairon/action/runtime/TrackerState.java:14-28 — TrackerState does not model `paused` at all (no field, no default); low impact since no action reads it. |
| R1 | A tracker missing `stack` is treated as `[]` | action-server/src/main/java/com/kairon/action/runtime/TrackerState.java:31-41 — stack is not modelled. |
| R1 | A tracker without `active_loop` but with `active_form` uses the `active_form` value as the | action-server/src/main/java/com/kairon/action/runtime/TrackerState.java:31-41 — active_loop/active_form are not parsed; no active_form fallback exists. |
| R1 | A tracker without `sender_id` returns HTTP 500 and executes no action (same path as a miss | action-server/src/main/java/com/kairon/action/server/ActionProcessor.java:42-51 — Missing sender_id yields senderId=null and the action still executes with HTTP 200; no 500 path exists. |
| R1 | A tracker without both `active_loop` and `active_form` uses `{}` as the active loop | action-server/src/main/java/com/kairon/action/runtime/TrackerState.java:31-41 — active_loop is not modelled, so no {} default is applied. |
| R3 | A body that is a JSON object without a `tracker` key (and with a non-blank `next_action`)  | action-server/src/main/java/com/kairon/action/server/ActionProcessor.java:39-41 — Missing tracker throws IllegalArgumentException mapped to HTTP 422 envelope at WebhookController.java:61-63; test missingTrackerIs422 asserts 422 (WebhookTest.java:180-188). |
| R3 | A body that is not a JSON object, or is empty, returns HTTP 200 with body `{"success":fals | action-server/src/main/java/com/kairon/action/server/WebhookController.java:48-50 — Empty body returns status 422 with message as a string; non-object JSON also 422 (Jsons.readMap throws), and a literal 'null' body becomes {} and returns 200 null; test emptyBodyIs422 asserts 422. |
| R3 | No request to `/webhook` returns HTTP 422 as the status code | action-server/src/main/java/com/kairon/action/server/WebhookController.java:49,62,72-79 — error() sets HttpStatus 422 as the real status code for empty body, bad JSON and missing tracker. |
| R4 | A request without `X-Kairon-Request-ID` gets a response with an `X-Kairon-Request-ID` valu | action-server/src/main/java/com/kairon/action/server/SecurityFilter.java:26-28 — No UUID is generated when the header is absent; the response has no X-Kairon-Request-ID. |
| R4 | CORS allows credentials, all methods and all headers | action-server/src/main/resources/application.yml:13-16 — allowed-methods restricted to GET/POST/OPTIONS; allow-credentials not configured explicitly. |
| R4 | Each secure-header value equals the value captured from the Python server for the same req | action-server/src/main/java/com/kairon/action/server/SecurityFilter.java:22-25 — Six required secure headers are absent, and CSP value 'frame-ancestors 'none'' is not shown to match the Python capture. |
| R4 | Responses carry `Strict-Transport-Security`, `Content-Security-Policy`, `Referrer-Policy:  | action-server/src/main/java/com/kairon/action/server/SecurityFilter.java:22-25 — Only X-Content-Type-Options, Referrer-Policy, Content-Security-Policy, Cache-Control are added; HSTS, Permissions-Policy, Server: Secure, COEP, COOP, CORP are missing. |
| R4 | `Access-Control-Allow-Origin` equals the request `Origin` header when present, else the fi | action-server/src/main/resources/application.yml:6-17 — Relies on Micronaut CORS with allowed-origins '*'; no fallback to the first configured origin when Origin is absent (CORS headers only on CORS requests). |
| R6 | A valid webhook request with a 20 MB tracker is processed and does not return HTTP 413 | action-server/src/main/resources/application.yml:1-17 — No micronaut.server.max-request-size override, so Micronaut's 10 MB default rejects a 20 MB body with 413. |

## Changelog
- 2026-10-26: Initial draft from approved design.
- 2026-10-26: Review iteration 1 fixes (dependency cycles, compose secrets, scheduling endpoint contract, failure-mail paths, missing sender_id, dependency graph).
- 2026-10-26: Brownfield gap pass against existing port: 16 [GAP], 3 [UNVERIFIED] markers added.
- 2026-10-26: Build wave 1: R3 c5 corrected to literal Python (prior utterances are kept on action failure); gap marker removed.
- 2026-10-30: [GAP] markers re-verified against tests
- 2026-10-30: Stale prompt/database Out of Scope line now points to cavekit-prompt-database-actions.md.
