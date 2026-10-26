---
created: "2026-10-26T12:44:00Z"
last_edited: "2026-10-26T14:00:00Z"
---

# Cavekit: Outbound Clients

## Scope
Every network side-effect primitive the actions use: the swallowing (async-style) HTTP exchange, the raising (sync-style) HTTP exchange, redirect and wire-format semantics, the pyscript and expression evaluator calls, SMTP, and media multipart upload. Which action calls which primitive is defined in the action kits.

See context/refs/research-brief-java-action-server-port.md for evidence.

## Requirements

### R1: Swallowing HTTP exchange
**Description:** Used by http_action and parallel children. Transport errors are swallowed and the action continues.
**Acceptance Criteria:**
- [ ] [GAP] The timeout is a wall-clock cap on the whole exchange (connect, redirects, body) equal to `ACTION_SERVER_REQUEST_TIMEOUT` seconds
- [ ] A connection refusal yields response body `null` and status `null` with no exception
- [ ] A timeout yields response body `null` and status `null` with no exception
- [ ] Exactly one request is sent per call, including for 502/503/504 responses (no retry)
- [ ] Statuses 200, 201, 202, 204 are treated as OK; a null status is not treated as a failure
- [ ] A request-timestamp header is added to each request
- [ ] Methods GET, PUT, POST and DELETE are supported
- [ ] Content type `json` sends a JSON body; content type `data` sends a form body
**Dependencies:** cavekit-config-and-deploy.md R1

### R2: Raising HTTP exchange
**Description:** Used by hubspot, razorpay and the expression evaluator. Non-2xx raises.
**Acceptance Criteria:**
- [ ] A non-2xx response raises an error whose text starts with `Failed to execute the url:`
- [ ] GET sends parameters in the query string
- [ ] Non-GET sends parameters as a JSON or form body per the content type
- [ ] A request-timestamp header is added to each request
**Dependencies:** none

### R3: Redirects and TLS
**Description:** Redirect handling matches the Python clients.
**Acceptance Criteria:**
- [ ] [GAP] Up to 10 redirect hops are followed; the 11th fails the exchange
- [ ] A 301, 302 or 303 response to a POST is followed with a GET and no body
- [ ] A 307 or 308 response is followed with the original method and body
- [ ] [GAP] `Authorization`, `Cookie` and `Proxy-Authorization` are not sent to a different origin after a redirect
- [ ] A server with an invalid TLS certificate fails the exchange
**Dependencies:** cavekit-config-and-deploy.md R5

### R4: Wire format
**Description:** Request bytes match what the Python clients send where downstreams may care.
**Acceptance Criteria:**
- [ ] JSON requests send `Content-Type: application/json` with no charset parameter
- [ ] [GAP] Form encoding of a nested dict value sends the nested dict's keys as the value, matching Python
- [ ] [GAP] Form encoding of a list value sends one repeated key per element
- [ ] [GAP] Form and query encoding drop keys whose value is null
- [ ] [GAP] Spaces in query strings are encoded as `+`
- [ ] [UNVERIFIED] Which downstreams depend on these wire details is confirmed (needs human review)
**Dependencies:** none

### R5: Pyscript evaluator
**Description:** Pyscript runs remotely via the configured pyscript URL.
**Acceptance Criteria:**
- [ ] The call is a POST of `{"source_code": ..., "predefined_objects": ...}` to the pyscript URL configured under the async-callback pyscript key
- [ ] A response whose `statusCode` is not 200 raises
- [ ] Result slots exclude the `bot` key
- [ ] Output is `bot_response` from the body, else the body, else `{}`
- [ ] When the body carries `media_ids`, they are appended to the output
**Dependencies:** cavekit-templating-and-secrets.md R4, cavekit-config-and-deploy.md R1

### R6: Expression evaluator
**Description:** Expression evaluation runs remotely via the configured evaluator URL.
**Acceptance Criteria:**
- [ ] The call is a POST of `{"script": ..., "data": ...}` to the evaluator URL
- [ ] A response `{"success": true, "data": X}` yields `X`
- [ ] A response with `success: false` raises an error starting with `Expression evaluation failed:`
- [ ] A non-2xx response raises per R2
**Dependencies:** R2, cavekit-config-and-deploy.md R1

### R7: SMTP
**Description:** Mail is sent with the configured SMTP settings.
**Acceptance Criteria:**
- [ ] [GAP] Mail uses the resolved host, port, user, password and TLS flag
- [ ] [GAP] One message is sent per recipient
- [ ] [GAP] The subject is `{sender_id} {subject}`
- [ ] [GAP] The body is HTML, either the chat-log template or the custom text
**Dependencies:** cavekit-templating-and-secrets.md R3

### R8: Media multipart upload
**Description:** When the request body carries `media_ids`, each media item is fetched and the request is sent as multipart.
**Acceptance Criteria:**
- [ ] [GAP] A body with two `media_ids` produces one multipart request containing two file parts
- [ ] [UNVERIFIED] The multipart request matches the recorded Python request in method, URL and part names
- [ ] [UNVERIFIED] Media fetch, size validation and part naming match the Python source (needs human review)
**Dependencies:** R1

## Out of Scope
- Lambda transports for pyscript and web search
- LLM and vector-store clients (prompt_action, database_action)
- LLM rephrase, native image
- Adding retries (Python effectively has none)
- User-Agent and header-order parity

## Cross-References
- See also: cavekit-templating-and-secrets.md
- See also: cavekit-dispatch-and-logging.md
- See also: cavekit-core-actions.md
- See also: cavekit-integration-actions.md
- See also: cavekit-orchestration-actions.md
- See also: cavekit-config-and-deploy.md

## Source Traceability
- R1: kairon/shared/rest_client.py:51-70; kairon/shared/actions/utils.py:~60-81 (execute_request_async)
- R2: kairon/shared/actions/utils.py:98-143 (execute_http_request)
- R3: kairon/shared/rest_client.py (aiohttp allow_redirects defaults)
- R4: kairon/shared/actions/utils.py:98-143; kairon/shared/rest_client.py
- R5: kairon/shared/actions/utils.py:759-785 (run_pyscript), 1101-1123 (evaluate_pyscript), 719-724
- R6: kairon/shared/actions/utils.py:1086-1097 (evaluate_script)
- R7: kairon/shared/utils.py:2738 (trigger_email); kairon/actions/definitions/email.py:62-71
- R8: kairon/shared/actions/utils.py:162-232 (process_media_and_execute_requests, validate_media_sizes)

## Gap Summary
Brownfield verification against the existing port (2026-10-26): 24 met, 12 gaps, 3 unverified by code reading.
Criteria prefixed `[GAP]` are not satisfied by the current code; `[UNVERIFIED]` need runtime, fixture, or human confirmation.

| Req | Gap | Evidence |
|---|---|---|
| R1 | The timeout is a wall-clock cap on the whole exchange (connect, redirects, body) equal to  | action-server/src/main/java/com/kairon/action/support/HttpCaller.java:96 — Uses java.net.http per-request timeout from KAIRON_ACTION_TIMEOUT (application.yml:26), which covers up to the response headers only (not the body) and is applied per hop, not as a whole-exchange wall clock. |
| R3 | Up to 10 redirect hops are followed; the 11th fails the exchange | action-server/src/main/java/com/kairon/action/support/HttpCaller.java:30 — Redirect.NORMAL uses the JDK default limit (jdk.httpclient.redirects.retrylimit=5), not 10. |
| R3 | `Authorization`, `Cookie` and `Proxy-Authorization` are not sent to a different origin aft | action-server/src/main/java/com/kairon/action/support/HttpCaller.java:83-115 — No explicit stripping of Authorization/Cookie/Proxy-Authorization on cross-origin redirect; relies on the JDK, which does not strip user-set headers. |
| R4 | Form and query encoding drop keys whose value is null | action-server/src/main/java/com/kairon/action/support/HttpCaller.java:129 — Query encoding drops nulls (:145-147), but form encoding sends key= with an empty string. |
| R4 | Form encoding of a list value sends one repeated key per element | action-server/src/main/java/com/kairon/action/support/HttpCaller.java:129 — A list becomes one key with Java '[a, b]', not repeated keys. |
| R4 | Form encoding of a nested dict value sends the nested dict's keys as the value, matching P | action-server/src/main/java/com/kairon/action/support/HttpCaller.java:129 — Form values use String.valueOf, so a nested dict becomes Java '{a=1}', not the dict's keys. |
| R4 | Spaces in query strings are encoded as `+` | action-server/src/main/java/com/kairon/action/support/HttpCaller.java:84,100 — withQuery uses URLEncoder (+), but URLs with spaces from placeholder substitution are passed raw to URI.create, which throws, so the exchange silently fails. |
| R7 | Mail uses the resolved host, port, user, password and TLS flag | action-server/src/main/java/com/kairon/action/actions/EmailAction.java:47-51 — No SMTP client exists (no mail/Transport anywhere); EmailAction only logs 'smtp is not configured'. |
| R7 | One message is sent per recipient | action-server/src/main/java/com/kairon/action/actions/EmailAction.java:47-51 — Loops per recipient but only logs; nothing is sent. |
| R7 | The body is HTML, either the chat-log template or the custom text | action-server/src/main/java/com/kairon/action/actions/EmailAction.java:67-75 — HTML is built, but the chat-log body is an ad-hoc template (ActionSupport.java:557-569), not Python's, and is never sent. |
| R7 | The subject is `{sender_id} {subject}` | action-server/src/main/java/com/kairon/action/actions/EmailAction.java:46 — The subject string is built correctly as '{sender_id} {subject}' but never sent. |
| R8 | A body with two `media_ids` produces one multipart request containing two file parts | action-server/src/main/java/com/kairon/action/support/HttpCaller.java:187-210 — multipart() sends one request per media file, each with a single 'file' part, rather than one request with two parts. |

## Changelog
- 2026-10-26: Initial draft from approved design.
- 2026-10-26: Review iteration 1 fixes (dependency cycles, compose secrets, scheduling endpoint contract, failure-mail paths, missing sender_id, dependency graph).
- 2026-10-26: Brownfield gap pass against existing port: 12 [GAP], 3 [UNVERIFIED] markers added.
