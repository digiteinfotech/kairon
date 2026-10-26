# Approved Design: Java Action Server Port (2026-10-26)

User decisions (locked):
- Scope: spec the Java action-server as a drop-in replacement for the Python kairon/actions server.
- Parity bar: same webhook response AND same Mongo action-log records AND same outbound side effects (HTTP, SMTP, callbacks, Mongo writes).
- Error contract: EXACT Python behaviour (200 + error envelope for validation; 200 + empty events on action failure; 500 on missing tracker; 200 null on blank next_action). Existing Java tests expecting 422 are wrong and must be corrected.
- schedule_action: new JSON endpoint on the Python events server writes the job. Java never writes the APScheduler pickle.
- prompt_action and database_action: DEFERRED to a later cycle (out of scope everywhere).
- Failure mail to support address: IN scope (fire-and-forget, never affects response/log).
- Parity fixtures: RECORDED from the pytest suite via a conftest recorder, replayed in Java.
- Native image: OUT of scope (JVM only).
- DB config: Java honours DATABASE_URL with default database `kairon`.
- Assumptions carried: Lambda trigger transports (pyscript, web_search) out of scope; bot_response LLM rephrase out of scope; media multipart in http_action in scope but flagged for human review.

Decomposition: Approach A, 10 layered domains.

## Domain 1: webhook-contract
Scope: HTTP surface Rasa talks to. Request parsing, tracker model, response envelope, error contract, middleware headers, health endpoints. No action logic.
- R1 Request acceptance: POST /webhook accepts {next_action, tracker, domain, version, trigger_info}; unknown keys ignored; tracker defaults per rasa_sdk (slots {}, latest_message {}, events [], paused false, followup_action null, active_loop falls back to active_form then {}, latest_action_name null, stack []). sender_id required. Version mismatch only logs.
- R2 Response envelope: {"events":[...],"responses":[...]}. Events are slot events only {"event":"slot","timestamp":null,"name","value"}, one per returned slot in insertion order, including null values. Each response carries all 8 rasa_sdk keys {text, buttons:[], elements:[], custom:{}, template, response, image, attachment} with defaults; extra kwargs merged top-level; utter_message(None) still appends a message with text null.
- R3 Error contract (exact Python): blank/whitespace next_action -> HTTP 200 body `null`. Missing tracker key -> HTTP 500. Non-object or invalid body -> HTTP 200 {success:false, error_code:422, message:[...], data:null}. Action-level failure -> HTTP 200 {"events":[],"responses":[]}.
- R4 Middleware: CORS from configured origins with credentials, all methods/headers; GZip; request id from X-Kairon-Request-ID or generated UUID4, echoed on response; full secure-header set Python emits (HSTS, CSP, no-referrer, permissions policy, Cache-Control must-revalidate, X-Content-Type-Options, Server: Secure, COEP require-corp, COOP same-origin, CORP same-origin; ACAO = request Origin else first allowed origin).
- R5 Health: GET / -> {"message":"Kairon Action Server Up and Running"}; GET /healthcheck -> {"message":"health check ok"}. No auth on any endpoint.
- R6 Request size: no body-size limit below what Python accepts (uvicorn unlimited; Micronaut default 10MB). Flag ceiling for human review.
Out of scope: action behaviour, logging, templating. Depends on: none. Depended on by: 5,6,7.

## Domain 2: dispatch-and-logging
Scope: name -> action type resolution, execution, catch-all failure path, action_server_logs record contract.
- R1 Type resolution: "kairon_voice_disconnect" by literal name; names starting "utter_" -> bot response; else lookup in `actions` by bot + name + status true, CASE-SENSITIVE (no lowercasing of next_action). Missing -> failure "No action found for given bot and name". Unknown type -> "<type> type action is not supported with action server".
- R2 Bot slot mandatory: empty bot slot or action name -> failure "Bot id and action name not found in slot".
- R3 Catch-all: any exception escaping an action -> write Failed log with NO `type` field (intent, action, sender, exception text, bot, request_id, timestamp, status Failed, default trigger_info), fire failure mail, return empty events. Never propagates.
- R4 Log record base: every log carries intent (fallback-inclusive, from latest message), sender, user_msg, trigger_info (default {trigger_name:"", trigger_type:"implicit", trigger_id:""}; taken from request trigger_info when present), request_id, bot, timestamp (UTC, millisecond precision), status Success|Failed. Collection name `action_server_logs`. Field insertion order matches Python declaration order then dynamic fields.
- R5 Per-type log fields: enumerate the additional fields per action type from the research brief matrix (Per-Action Side-Effect Matrix), including the heterogeneous http_action events[] sub-documents ({type:slots},{type:response},{type:api_call,...},{type:dynamic_params|params_list},{type:filled_slots,...}) and the empty pre-created parent record of parallel_action.
- R6 Failure mail: on any failure path, best-effort mail to the configured support address with action name, bot, exception, stack trace, slot values, latest user text; never affects response or log; own failures swallowed. Flag template fidelity for human review.
- R7 Double-log case: store_page empty-identifier path yields two records (action's own Failed record + catch-all record).
Out of scope: templating, outbound clients, action implementations. Depends on: 1. Depended on by: 5,6,7.

## Domain 3: templating-and-secrets
Scope: pure transformations config+tracker -> strings, plus crypto those need.
- R1 URL/text placeholder grammar, exact order: $SENDER_ID, $INTENT (blank if none), $USER_MESSAGE, then $$name (key vault, blank if missing), then remaining $name (slot, blank if null). User message = kairon_user_msg entity when text starts with "/". Regex `\$\w+` also matches inside query strings.
- R2 Response template grammar: ${RESPONSE} = whole body serialized as Python json.dumps would. ${a.b.0} dotted path (dict keys, integer list indices); dict values -> JSON, else str(). Non dict/list body with a template raises "Could not find value for keys in response". Empty template returns raw body.
- R3 Parameter resolution types: value, slot, sender_id, user_message, intent, chat_log ({sender_id, session_started, conversation}), key_vault, latest_message. Encrypted `value` params decrypted before use and masked in logs with configured unmasked char count. Missing key-vault key -> null, no error.
- R4 Evaluation context keys: sender_id, user_message, slot, intent, chat_log, key_vault (when requested), latest_message, kairon_user_msg entity, session_started, bot.
- R5 Fernet: decrypt Python-produced tokens and produce tokens Python decrypts. No TTL enforcement. Verified against public Fernet spec vectors + cross-language round trip. Invalid tokens raise.
- R6 JWT: mint HS256 tokens matching PyJWT output for store-page token (sub=sender, bot, access_limit regex list: /api/bot/.+/customer_data/.*, /store_page/metadata, /data/collection/.*, /store_page/exec/flow) and agent integration token (15 min expiry, sub=sender, bot). Header order (typ, alg) and integer exp match.
- R7 Python repr + json.dumps parity: a serializer reproducing str(dict) (single quotes, True/False/None) and json.dumps defaults (", " and ": " separators, ASCII escaping, float formatting) for log fields that store them (two_stage bot_response, voice_disconnect bot_response, bot_response action bot_response, database payload/response). Verified against strings captured from Python.
- R8 Sender id: a sender id that is a valid Fernet token is decrypted; otherwise used as-is.
Out of scope: HTTP calls, which action uses which template. Depends on: none. Depended on by: 5,6,7.

## Domain 4: outbound-clients
Scope: every network side-effect primitive.
- R1 Async-style HTTP (http_action, parallel children): timeout = wall-clock cap on whole exchange (default action.request_timeout 60s; 1s if key absent). Transport errors SWALLOWED: body null, status null, action continues. No retry. OK statuses {200,201,202,204}. Adds request-timestamp header. Methods GET/PUT/POST/DELETE; content type json or form.
- R2 Sync-style HTTP (hubspot, razorpay, expression evaluator): any non-2xx raises "Failed to execute the url: ...". GET params in query; others json or form body. Adds request-timestamp header.
- R3 Redirects: follow up to 10 hops; 301/302/303 on POST -> GET and drop body; 307/308 keep method+body; Authorization not forwarded cross-origin. TLS verification on.
- R4 Wire format: application/json with no charset. Form encoding reproduces Python lossy nested-dict behaviour (nested dict -> its keys), lists -> repeated keys, null values dropped, spaces as `+` in queries. Flag for human review on which downstreams care.
- R5 Pyscript evaluator: POST {source_code, predefined_objects} to configured pyscript URL (the async-callback pyscript key); expect {statusCode, body}; non-200 statusCode raises. Result slots exclude `bot`. Output = bot_response, else body, else {}. media_ids appended to output when present.
- R6 Expression evaluator: POST {script, data} to configured evaluator URL; expect {success, data}; success:false raises "Expression evaluation failed: ...".
- R7 SMTP: send with configured host/port/user/password/TLS; one message per recipient; subject prefixed with sender id; HTML body from chat-log template or custom text.
- R8 Media upload: when body carries media_ids, fetch each media item and send multipart. Flag for human review (Python source only partly mapped).
Out of scope: Lambda transports, LLM/vector clients. Depends on: 3. Depended on by: 5,6,7.

## Domain 5: core-actions (7 actions, no external integration)
- R1 slot_set: FROM_VALUE sets value, other types set null. No utterance, no kairon_action_response. Log messages "Setting slot 'x' to 'y'." / "Resetting slot 'x' value to None.". Always Success.
- R2 form_validation: config matched on tracker requested_slot; empty requested slot -> {} no log. Validation via expression evaluator when semantic set. Valid -> slot value (slot_set.value, or another slot's value if type != custom), valid_response uttered if non-empty. Invalid -> slot null, invalid_response uttered, log status Failed. Log action = tracker followup_action.
- R3 two_stage_fallback: buttons from training examples per ranked intent (or text search) + rule buttons with payload `/<payload>{"kairon_user_msg": "<msg>"}`; no recommendations -> utter response "utter_default". Returns {}. Log bot_response = Python repr of recommendations list.
- R4 bot_response (utter_*): utters {"response": "<utter_name>"}; kairon_action_response = that dict. LLM rephrase out of scope; log still carries enable_rephrasing:false, is_rephrased:false, raw_gpt_response null.
- R5 voice_disconnect: utter_custom_json {"disconnect": true}; returns {}; log bot_response = Python repr of that dict.
- R6 store_page: encrypts identifier slot (Fernet), mints store-page JWT. Slots user_identifier, temp_token, store_page_name, callback_identifier. Empty identifier re-raises (two log records, no events). Other errors -> empty slots, Failed log. No bot_response in log.
- R7 callback: writes CallbackData record (action_name, callback_name, bot, sender_id, channel, metadata, identifier uuid7 hex, callback_url, timestamp, is_valid true). URL = async callback base + ("s/{token}" standalone else "d/{identifier}/{token}"). Returns {dynamic_url_slot_name: identifier if standalone else url}. Utters bot_response with {callback_url} substituted if dispatch (default true). No kairon_action_response.
Depends on: 1,2,3. Out of scope: rephrasing via LLM.

## Domain 6: integration-actions (13 actions, one external system each)
- R1 http: full 8-step flow (config; context; headers; body from dynamic pyscript or param list; URL templating; request; response composition expression|script; slot filling with per-slot independent failure -> null + log, time_taken of last slot only). Dispatch only when configured AND response truthy; json dispatch falls back to text on decode error with log message "Failed to convert http response to json: ..."; list responses -> one message per element (dict -> custom json, else text). Slots always include kairon_action_response and http_status_code, plus dynamic_params slots then set_slots (override). Failure utterance "I have failed to process your request". Expression-mode response composition validates status first (non-2xx fails). Log events[] sub-docs and time_elapsed = sum of four timings; fail_reason on non-2xx.
- R2 email: one SMTP send per recipient; subject "{sender_id} {subject}"; chat-log HTML or custom_text; from/to resolved as value or slot; smtp creds via param resolution. Utters bot_response if dispatch (default true). Failure "I have failed to process your request".
- R3 google_search / R4 web_search: ALWAYS utter; default failure_response replaced by formatted results on success; optional set_slot + kairon_action_response. Search term from latest message or kairon_user_msg entity when text starts "/". Log fields google_response / public_search_action_response.
- R5 jira ("I have failed to create issue for you"; summary "{sender_id} {summary}"; description = message trail), R6 zendesk (same failure text; comment = chat-log HTML), R7 pipedrive ("I have failed to create lead for you"; lead + org + person + note), R8 hubspot ("I have failed to process your request"; POST https://api.hsforms.com/submissions/v3/integration/submit/{portal}/{guid}; log request_params + api_response), R9 razorpay (POST https://api.razorpay.com/v1/payment_links/ basic auth; body {amount:int, currency, customer{...}, notes{..., bot}}; response short_url; non-whole amount -> exception "amount must be a whole number! Got X."; log request + api_response). All unconditional utterance + kairon_action_response.
- R10 live_agent: availability check first (unavailable -> message, no raise). POST {live-agent-url}/conversation/request {bot_id, sender_id, channel, request_id} Bearer token; non-200 raises. Web channel (no channel key) sends JSON {"action":"live_agent","response":...}; other channels text; dispatch false still sends JSON with null response. Returns {}.
- R11 agent: POST {simple-agent-url}/agents/{bot}/{agent_id}/run/{sender}/simple body {message, session_id:null, metadata:{}, max_iterations:1}; headers X-user + Bearer integration JWT; non-2xx raises. Utters api_response["output"] or str(api_response). Failure "I have failed to process your request.". Log url, api_response.
- R12 voice_call: initiate outbound call via configured telephony provider (Twilio first) with call URL + status URL; write ChannelLogs {type voice, status "initiated", data{to, call_sid}, message_id = call_sid or "unknown", bot, user, initiator "bot"}. Utters response (default "I'm placing a call to you now.") if dispatch. Failure "I have failed to place the call". Flag provider coverage for human review.
- R13 pyscript: run pyscript evaluator; return its slots minus bot + kairon_action_response; utter per dispatch_response with response.type (json|text) and response.bot_response; failure "I have failed to process your request"; log carries full config + messages.
Depends on: 1,2,3,4. Out of scope: prompt_action, database_action, Lambda transports.

## Domain 7: orchestration-actions
- R1 parallel: pre-create EMPTY log record to obtain trigger_id. Fan out N POSTs to the server's own webhook with next_action replaced and trigger_info{trigger_name, trigger_type:"parallel_action", trigger_id}, propagating request id header. Child utterances discarded; only child slot events merged, last write wins. Child failures never fail parent (parent Success). response_text dispatched only if dispatch_response_text; kairon_action_response set only then. Parent log later filled (type, action, sender, bot_response, exception, status, user_msg, trigger_info, request_id); children log with trigger_info.trigger_id = parent id. Fan-out must not starve request pool (flag sizing for human review).
- R2 schedule: resolve schedule_time (param), timezone, callback config, params. Submit job through Domain 8 endpoint (never write Mongo job store directly). Then call events dispatch endpoint. Utters response_text if dispatch; failure "Sorry, I am unable to process your request at the moment.". Log schedule_action, schedule_time, timezone, execution_info, data, bot_response, messages. Returns {}.
Depends on: 1,2,3,4,8.

## Domain 8: events-schedule-api (Python events server)
- R1 Endpoint: JSON request with job id, run time (UTC), timezone, schedule type (pyscript|flow), target name, resolved params. Writes job through the scheduler's own job store (executor default, misfire_grace_time 7200, coalesce true, max_instances 1, name execute_task, same executor function + args as today's direct write).
- R2 Equivalence: job created via endpoint executes identically to one created by today's direct write.
- R3 Dispatch wake: existing GET /api/events/dispatch/{id} keeps working.
- R4 Validation: reject missing fields / unknown schedule types with the server's existing error envelope. Same auth posture as other events endpoints (none today beyond network isolation; flag for human review).
- R5 Migration: Python action server's schedule action switches to the endpoint too (single writer).
Depends on: none. Depended on by: 7.

## Domain 9: parity-harness
- R1 Recorder: pytest-side hook, no edits to existing tests, captures per test node: Mongo seed docs, inbound webhook request, every mocked upstream request + canned response, webhook response, Mongo docs written during the test. One JSON fixture per node id. Volatile fields (timestamps, ObjectIds, UUIDs, JWTs) normalized/masked with placeholders.
- R2 Fixture format: documented, versioned schema; canonical extended JSON for BSON types.
- R3 Replay: one parameterized Java test per fixture: seed catalog, register upstream stubs, POST request, assert response (ignoring normalized fields), assert every outbound call made with recorded method/URL/headers-of-interest/body, assert written log docs match ignoring _id and timestamps.
- R4 Two backends: same replay runs against in-memory catalog and real MongoDB container.
- R5 Coverage report: parity percentage against the 434-node list by action type; lists untranslatable nodes (Python-internal patches) with reasons.
- R6 Gate: CI fails if any previously passing fixture regresses.
Depends on: none (consumes 1-7 output). Flag untranslatable node triage for human review.

## Domain 10: config-and-deploy
- R1 Config mapping: every Python key the action server reads has a Java equivalent with same env var name + default: DATABASE_URL (default DB kairon), ACTION_SERVER_REQUEST_TIMEOUT, pyscript URL from async-callback key, evaluator URL, events server URL, async callback base URL, live agent URL/token/enabled, simple-agent URL, voice-call URL, web-search URL, support mail, CORS origins, Fernet key, JWT secret/algorithm, unmasked char count.
- R2 No shipped secrets: no default values for Fernet key, JWT secret, AES key; startup fails loudly if absent.
- R3 Mongo representation: UUID representation Python-legacy; dates as BSON dates at millisecond precision; collection names match mongoengine defaults (actions, action_server_logs, http_action_config, key_vault, bot_settings, slots, and the per-type config collections).
- R4 Compose swap: kairon-action-server service in docker-compose switches to the Java image with no other file changes, port 5055.
- R5 Dependency hygiene: HTTP client not affected by GHSA-q6gh-6v2r-hjv3 (Micronaut >= 4.10.24).
- R6 Blocking execution: blocking work (Mongo, SMTP, outbound HTTP) off the event loop with a pool large enough for parallel fan-out.
Depends on: none. Out of scope: native image, Kubernetes manifests.

## Dependency order
1 webhook-contract, 3 templating-and-secrets, 8 events-schedule-api, 9 parity-harness, 10 config-and-deploy (no deps) -> 2 dispatch-and-logging (1) -> 4 outbound-clients (3) -> 5 core-actions (1,2,3) -> 6 integration-actions (1,2,3,4) -> 7 orchestration-actions (1,2,3,4,8)
