# Research Brief: Java Action Server Port

Generated: 2026-10-26
Agents: 8 (4 codebase, 4 web)

## Summary
The port replaces the Python FastAPI action server (`kairon/actions/`, 24 Rasa-style action types, POST `/webhook` on :5055) with a Java 21 / Micronaut 4.10 service at `action-server/`, and must match it on three things: webhook responses, `action_server_logs` Mongo records, and outbound side effects (HTTP, SMTP, Mongo writes, callbacks). On paper the Java port is feature-complete: all 24 action classes exist (~4.8k LOC, no stubs). Verification is far behind, though: about 22 hand-written parity tests, against 434 Python pytest nodes that are listed in `python-action-nodes.txt` and never run. The biggest parity risks:
1. `schedule_action` writes a pickled APScheduler job into Mongo, and Java cannot safely produce that pickle.
2. The many character-exact details: the hand-rolled `$slot`/`${a.b.0}` templating, `str(dict)` Python-repr strings in log fields, the 8-key rasa_sdk message dict and `timestamp:null` slot events.
3. The error contract. Python returns HTTP 200 for almost every failure, but the Java tests assert HTTP 422 for missing tracker and empty body.
4. HTTP wire and redirect semantics. Micronaut http-client 4.10.22 (the version in use) is vulnerable to GHSA-q6gh-6v2r-hjv3.

Research recommends the following:
- Mine the Python test suite into JSON golden fixtures with a conftest recorder, and replay them in Java with WireMock journals and JsonUnit.
- Bump Micronaut to >= 4.10.24.
- Hand-roll the interpolator, Fernet, HS256 JWT and PyRepr.
- Delegate pyscript over HTTP. Never use GraalPy.
- Never write the pickle from Java. Use a Python shim or a new JSON scheduling endpoint on the events server instead.

## Key Findings

### Architecture & Patterns

**Dispatch chain** (high): POST `/webhook` (`actions/server.py:~315-333`) -> `ActionHandler.process_actions` (`actions/handlers/action.py:11-35`) -> `ActionProcessor.process_action` (`actions/handlers/processor.py:17-48`) -> `ActionFactory.get_instance` (`actions/definitions/factory.py:30-58,68-73`) -> `ActionX.execute(dispatcher, tracker, domain, **kwargs)`. Actions return a dict of slots only and never events. The processor emits `[SlotSet(k,v) for k,v in slots.items()]`.
- Type resolution (`shared/actions/utils.py:507-532`) checks in this order:
  1. The name `kairon_voice_disconnect`.
  2. The case-sensitive `utter_` prefix, which maps to `kairon_bot_response`.
  3. `Actions.objects(bot=, name=, status=True).get().type`. If that raises DoesNotExist, the result is ActionFailure("No action found for given bot and name").
- An unknown type raises ActionFailure("<type> type action is not supported with action server"). The 24 types are listed in `shared/actions/models.py:32-56`.
- `next_action` is only stripped, never lowercased, on lookup. `Actions.clean` lowercases on write (`data_objects.py:297-298`), so a mixed-case `next_action` produces "not found" (high).
- The `bot` slot is mandatory. If it is empty, the result is ActionFailure("Bot id and action name not found in slot").

**Request contract** (high): `{next_action, tracker, domain, version, trigger_info?, ...}`, with extra keys ignored.
- `version` triggers a warning only (`check_version_compatibility`).
- `Tracker.from_dict` (rasa_sdk `interfaces.py:24-36`) reads the following keys:
  - `sender_id` (required)
  - `slots{}`
  - `latest_message{text, intent.name, entities}`
  - `events[]`
  - `paused`
  - `followup_action`
  - `active_loop`, falling back to `active_form`
  - `latest_action_name`
- `domain` defaults to `{}`. The HTTP action does not use it, but `kairon_bot_response` reads `domain["responses"]`.
- Rasa SDK >= 3.9 may omit `domain` and send `domain_digest` instead [source: https://rasa.com/docs/reference/api/pro/action-server-api/]. It is unknown whether Kairon's Rasa sends it. The Java config pins rasa-sdk-version "3.6.21".
- `build_context` (`shared/actions/utils.py:360-384`) is the context passed to the evaluator and pyscript. Its keys are `sender_id`, `user_message`, `slot`, `intent`, `chat_log`, `key_vault` (all decrypted secrets), `latest_message`, `KAIRON_USER_MSG_ENTITY` and `session_started`.

**Response contract** (high): `{"events":[...], "responses":[...]}` (rasa_sdk `executor.py:377-381`).
- Events are slot events only: `{"event":"slot","timestamp":null,"name":k,"value":v}` (rasa_sdk `events.py:44-47`). Every returned key is emitted, including None values and system slots (`kairon_action_response`, `http_status_code`, `llm_call_id`). Order is dict insertion order. `validate_events` drops dicts that lack `event`. No BotUttered events are emitted.
- Each message has exactly 8 keys, in this order: `{"text","buttons":[],"elements":[],"custom":{},"template","response","image","attachment"}`. Any extra kwargs are merged at the top level (rasa_sdk `executor.py:34-66`).
- `utter_message(None)` still appends a message, with `text:null` and the other keys at their defaults (high, RESOLVED).
- `json_message` goes to `custom`. `text` is `str(response)`.

**Error-handling contract** (high, verified against `server.py:162-262` and `handlers/action.py`):
| Case | HTTP | Body | Side effects |
|---|---|---|---|
| Any exception inside an action/processor (incl. ActionFailure, unknown type, missing action) | 200 | `{"events":[],"responses":[]}` | Failed `action_server_logs` record with **no `type`** (intent, action, sender, exception=str(e), bot, status, request_id) + fire-and-forget failure mail (`processor.py:34-48`) |
| Blank/missing `next_action` | 200 | `null` | none |
| Missing `tracker` key | 500 (KeyError, no handler; mongoengine `LookUpError` != builtin) | Starlette default | none |
| Body validation (non-object, empty) | 200 | `{"success":false,"error_code":422,"message":exc.errors(),"data":null}` | none |
| StarletteHTTPException / AssertionError / DoesNotExist / PyMongoError / mongoengine errors / PyJWTError / AppException | 200 | `{success:false, error_code:<int>, message:str, data:null}` | none |
| ActionExecutionRejection / ActionNotFoundException | 400 | `{"error","action_name"}` | Not raised by Kairon |
Within-action failures are mostly swallowed: the action utters its fallback text, writes a Failed log, sends the failure mail and returns HTTP 200 with slots. Some paths therefore write two log records. For example, an empty identifier in `store_page_action` re-raises (`store_page.py:69-71`), and the processor then writes a second generic record. The Java test `emptyStorePageIdentifierLogsTwice` covers this.

**Templating grammar** (high, character-exact, no jinja):
- `prepare_url` (`utils.py:458-492`) replaces placeholders in this order:
  1. `$SENDER_ID`
  2. `$INTENT` (blank if None)
  3. `$USER_MESSAGE` (the `kairon_user_msg` entity if the text starts with "/")
  4. `$$name` (key vault, blank if missing)
  5. Each remaining `\$\w+` (slot, blank if None)
- `prepare_response` (`utils.py:608-675`) handles response templates:
  - `${RESPONSE}` becomes `json.dumps(data)`.
  - `${a.b.0}` is a dotted path, where each segment is a dict key or an int list index. A dict value is rendered with `json.dumps` and anything else with `str()`.
  - If the response is not a dict or list, it raises "Could not find value for keys in response".
  - An empty template returns the raw response.
- `get_parameter_value` (`utils.py:254-289`) resolves these parameter types: `value|slot|sender_id|user_message|intent|chat_log({sender_id,session_started,conversation})|key_vault|latest_message`. With `encrypt` set on a value, it Fernet-decrypts. Logged values are masked with `Utility.get_masked_value`. A missing `key_vault` value becomes None (raise_err=False).
- The expression context is `{"data","context","http_status_code","response_headers"}`. In expression mode, `compose_response` (`utils.py:788-806`) first calls `validate_http_response_status(raise_err=True)`.

**Pyscript and evaluator delegation** (high): these never run in process.
- `run_pyscript` (`utils.py:759-785`) POSTs `{source_code, predefined_objects: context}` to `async_callback_action.pyscript.url`, or calls AWS Lambda if `evaluator.pyscript.trigger_task` is set. A non-200 `statusCode` raises ActionFailure. The result is `resp["body"]`.
- `evaluate_pyscript` (`utils.py:1101-1123`) flattens `data`, `response_headers` and `http_status_code`. Its output is `bot_response`, else `body`, else `{}`.
- `evaluate_script` (`utils.py:1086-1097`) is used for form validation and HTTP expression mode. It POSTs `evaluator.url` with `{script, data}` and expects `{success, data}`. `success=false` raises "Expression evaluation failed: ...".
- Exception: the LLM call in `prompt_action` IS in process (`LLMProcessor.predict` + litellm + Qdrant). This resolves the tests-agent's guess that pyscript might run in process.

**Slot semantics** (high):
- Every key is emitted, including None.
- These actions set `kairon_action_response` even when nothing is dispatched: http, email, google, web_search, jira, zendesk, pipedrive, hubspot, razorpay, prompt, pyscript, database, voice_call, agent and bot_response.
- These actions do not set it: slot_set, form_validation, live_agent, callback, schedule, two_stage_fallback, voice_disconnect and store_page. parallel sets it only when it dispatches.
- `filter_out_kairon_system_slots` (`utils.py:719-724`) drops only `bot`, and only from pyscript outputs.
- `fill_slots_from_response` (`utils.py:809-824`) evaluates each slot independently. A failure sets that slot to None and is logged without failing the action. The logged `time_taken` is from the last slot only.
- HTTP action order: dynamic_params slots, then `kairon_action_response`, then `http_status_code`, then set_slots overrides.

**Dispatch rules** (med-high):
- `handle_utter_bot_response` (`utils.py:678-716`) does nothing if `bot_response` is falsy. It dispatches only when `dispatch` is true and `bot_response` is truthy.
- With `dispatch_type=json`, it calls `json.loads` on a string and sends the result as `json_message`. On a decode error it falls back to text and logs `Failed to convert http response to json: ...`.
- With text, a list produces one message per element: a dict goes to `json_message`, anything else to `str()` text.
- The plain-utter actions (email, jira, zendesk, pipedrive, hubspot, razorpay, google, web_search, database, schedule, agent, voice_call) send raw text. A None value produces a `text:null` message.

**Timeouts, retry and swallowing** (med-high):
- `action.request_timeout` is 60s (`system.yaml:96`, env `ACTION_SERVER_REQUEST_TIMEOUT`). If the key is absent, the code defaults to 1s.
- The async client (`shared/rest_client.py:51-70`) uses aiohttp_retry `ExponentialRetry(attempts=1, statuses={104,502,503,504})`, so there is effectively no retry. `ClientTimeout(total=)` is a hard wall-clock cap.
- `execute_request_async` swallows transport exceptions (`utils.py:~79-81`) and returns `http_response=None`, possibly with `status=None`. `validate_http_response_status` ignores a falsy status. OK statuses are 200, 201, 202 and 204.
- The sync `execute_http_request` (`utils.py:98-143`) is used by hubspot, razorpay and evaluate_script. It raises "Failed to execute the url: ..." on non-2xx and adds `REQUEST_TIMESTAMP_HEADER`. GET uses `params=`, other methods use `json=`/`data=`. Hubspot and razorpay block the event loop.
- Parallel children use bare aiohttp with no timeout.

**Failure logging and mail** (high):
- Every action saves `ActionServerLogs` from a `finally` block with `Success` or `Failed`. The constants `Partial_Success` and `PASSED` exist but are unused by actions.
- `trigger_action_failure_mail` (`utils.py:1140-1156`) runs as an asyncio task that sends to `support_mail`, with the stack trace, slot values and user_query_history. Its own failures are swallowed.
- When `prompt_action` fails because FAQ is disabled, no mail is sent.

**Loopback and nesting** (med):
- `parallel_action` pre-creates an empty log record (`custom_parallel_actions.py:76-78`). It then uses `asyncio.gather(return_exceptions=True)` to POST its own `action.url` (default `http://localhost:5055/webhook`). Each child body is the original call with `next_action` replaced and `trigger_info{trigger_name, trigger_type:"parallel_action", trigger_id:<parent log id>}`, and `x-request-id` is propagated.
- Only `event=="slot"` from the children is merged, last write wins. Child utterances are discarded, and the parent stays `Success`.
- `prompt_action` runs action-source prompts in process (`prompt.py:193-200`), and each nested action writes its own log. Only http, callback, schedule, live_agent, google, agent and parallel expose `is_success`/`response`. Other action types raise AttributeError.

**Mongo and logs** (high):
- Collections use mongoengine default names with no meta overrides: `actions`, `action_server_logs`, `http_action_config`, `key_vault`, `bot_settings`, `slots`. Other per-type config collections are derived (med).
- `ActionServerLogs` is a DynamicDocument (`data_objects.py:263-282`):
  - Declared fields: `type, intent, action, sender, headers, url, request_method, request_params, api_response, bot_response, exception, messages, bot, timestamp(utcnow), status, trigger_info{trigger_name:"",trigger_type:"implicit",trigger_id:""}, request_id`.
  - Indexes: `bot` and `(bot,-timestamp)`.
- `request_id` comes from the `X-Kairon-Request-ID` header or uuid4 (`shared/middleware.py`) and is echoed on the response.

**Config and secrets** (high):
- Config: `system.yaml` is loaded via `ConfigLoader(os.getenv("system_file"))` with `${ENV:default}` interpolation (`shared/utils.py:267-275`). Mongo connects via `database.url` (`Utility.mongoengine_connection`, `shared/utils.py:1084-1101`).
- Fernet uses `security.fernet_key` (`shared/utils.py:1391-1407`). KeyVault values are encrypted pre_save (`data_objects.py:1015-1018`).
- FLAG: `system.yaml` ships hard-coded default secrets (Fernet, AES key/IV under `async_callback_action.short_secret`, and the JWT `security.secret_key`). The Java port must not copy them.

**Server surface** (high):
- `/webhook` has no auth. `log_requests` parses Authorization only to log `rid=`.
- Middlewares: CORS (`cors.origin`, credentials, all methods), GZip, request-id, OTel, and secure headers (HSTS, CSP, no-referrer, Permissions-Policy, Cache-Control must-revalidate, X-Content-Type-Options, `Server: Secure`, COEP/COOP/CORP). ACAO is the request Origin, else `allowed_origins[0]`.
- `GET /` returns `{"message":"Kairon Action Server Up and Running"}`. `GET /healthcheck` returns `{"message":"health check ok"}`.

### Per-Action Side-Effect Matrix
Config is per-type documents keyed by bot + name/action_name with status=True. Every log record carries `intent`, `sender`, `user_msg`, `trigger_info`, `request_id` and `status`. "fail txt" is the failure utterance. KAR = `kairon_action_response`.

| Type (file) | Config | Outbound side effects | Emitted slots / utterances | Log fields (beyond common) |
|---|---|---|---|---|
| http_action (`http.py`) | HttpActionConfig: http_url, request_method, content_type json\|data, params_list, dynamic_params, headers, response{dispatch,dispatch_type,value,evaluation_type}, set_slots | optional pyscript (dynamic_params); user HTTP (multipart if media_ids); evaluator/pyscript for response + each set_slot; keyvault reads | utter only if response.dispatch; KAR, http_status_code, set_slots, dynamic slots; fail txt "I have failed to process your request" | type, action, url, request_method, bot_response, fail_reason, exception, http_status_code, time_elapsed (sum of 4), events[] {slots},{response},{api_call: masked headers, method, url, payload, response, status_code, time_elapsed, response_headers},{dynamic_params\|params_list},{filled_slots,data,slot_eval_log,time_elapsed} |
| slot_set_action (`set_slot.py`) | set_slots[{name,type,value}] | none | from_value -> value else None; no utter, no KAR | messages[] "Setting slot 'x' to 'y'." / "Resetting slot 'x' value to None."; status always Success |
| form_validation_action | FormValidationAction matched on requested_slot | evaluator POST if validation_semantic | {slot: value or None}; valid/invalid_response uttered if non-empty; empty requested_slot -> {} and NO log | action=tracker.followup_action, messages[], status Failed on miss |
| email_action | from/to (value\|slot), subject, smtp_*, tls, custom_text, response, dispatch_bot_response | SMTP per recipient; subject "{sender_id} {subject}"; body chat-log HTML or custom_text | utter if dispatch (default true); KAR; fail txt as http | bot_response, exception |
| google_search_action | api_key(param), search_engine_id, search_term, num_results, website, failure_response, set_slot | Google CSE (`utils.py:545`) | always utters; {set_slot}, KAR | google_response, bot_response, exception |
| web_search_action | topn, website, failure_response, set_slot | web_search.url or Lambda (`utils.py:570`) | always utters; set_slot, KAR | public_search_action_response, bot_response, exception |
| jira_action | url, user_name, api_token, project_key, issue_type, parent_key, summary, response | Jira issue create; summary "{sender_id} {summary}" | always utters; fail "I have failed to create issue for you"; KAR | bot_response, exception |
| zendesk_action | subdomain, user_name, api_token, subject, tags, response | Zendesk ticket, comment = chat-log HTML | same as jira | bot_response, exception |
| pipedrive_leads_action | domain, api_token, title, response, metadata | org + person + lead + note (`utils.py:1019-1073`) | always; fail "I have failed to create lead for you"; KAR | bot_response, exception |
| hubspot_forms_action | portal_id, form_guid, fields, response | sync POST api.hsforms.com/submissions/v3/integration/submit/{portal}/{guid}; non-2xx raises | always; fail as http; KAR | request_params, api_response, bot_response, exception |
| razorpay_action | api_key, api_secret, amount, currency, username, email, contact, notes | sync POST api.razorpay.com/v1/payment_links/ basic auth; notes += bot | utters short_url; "amount must be a whole number! Got X."; KAR | request, api_response, bot_response, exception |
| prompt_action | FAQ config + bot settings (enable_faq required), llm_prompts, hyperparameters, set_slots, failure_message, dispatch_response | in-process LLMProcessor/litellm; Qdrant; CognitionSchema + crud reads; NESTED actions; pyscript for slots; openrouter switch | utter text (buttons None) if dispatch; set_slots, KAR, llm_call_id; FAQ disabled -> FAQ_DISABLED_ERR, no mail | events[{llm_response},{slots_to_fill}], llm_response, llm_logs, kairon_faq_action_config, media_ids, llm_call_id, time_elapsed |
| pyscript_action | source_code, dispatch_response | run_pyscript | slots minus bot, KAR; utter by response.type json\|text | config(full), bot_response, messages[], exception |
| database_action | collection, db_type, payload[], response, failure_response, set_slots (enable_faq) | embedding + vector query `{bot}_{collection}{suffix}`; CognitionSchema; pyscript | utter if response.dispatch; set_slots, KAR | config, payload=str, response=str, bot_response, exception |
| live_agent_action | bot_response, dispatch_bot_response | availability check; POST {live_agent.url}/conversation/request {bot_id,sender_id,channel,request_id} Bearer | web: custom {"action":"live_agent","response":...}; other: text; dispatch false still sends response None; returns {} | bot_response, messages[], exception |
| callback_action | callback_name, metadata_list, dynamic_url_slot_name, bot_response, dispatch | Mongo insert CallbackData (identifier uuid7 hex, callback_url, is_valid True...); URL `async_callback_action.url + s/{token}` or `d/{id}/{token}`; no HTTP | {slot: identifier\|callback_url}; utter with {callback_url} substituted; NO KAR | callback_url, callback_url_slot, identifier, metadata[], bot_response, messages |
| schedule_action | schedule_action, type PYSCRIPT\|FLOW, schedule_time, timezone, params_list, response_text | Mongo insert into events job-store `{_id:uuid7, next_run_time, job_state: Binary(pickle)}`; GET {events.server_url}/api/events/dispatch/{_id} | utter response_text if dispatch; fail "Sorry, I am unable to process your request at the moment."; {} | schedule_action, schedule_time, timezone, execution_info, data, bot_response, messages |
| parallel_action | actions[], dispatch_response_text, response_text | N self-POSTs to action.url (no timeout) | child slots merged LWW; child utterances discarded; KAR only if dispatched | pre-created empty record, later filled; children trigger_id=parent |
| two_stage_fallback | text_recommendations{count,use_intent_ranking}, trigger_rules, fallback_message | Mongo reads of training examples | buttons {text,payload} + fallback_message; none -> response="utter_default"; payload `/<p>{"kairon_user_msg": "<msg>"}`; {} | bot_response=str(recommendations) |
| kairon_bot_response (utter_*) | BotSettings.rephrase_response, domain.responses | optional LLM rephrase (reads `./template/rephrase-prompt.txt`) | {"text": rephrased} or {"response": name}; KAR = that dict | enable_rephrasing, is_rephrased, raw_gpt_response, bot_response=str(dict) |
| voice_call_action | to_phone_number, telephony_provider, response, dispatch; voice channel config | provider initiate_call (Twilio default); ChannelLogs insert {type voice, status initiated, data{to,call_sid}, initiator bot} | utter (default "I'm placing a call to you now."); fail "I have failed to place the call"; KAR | bot_response, exception |
| kairon_voice_disconnect | none | none | custom {"disconnect": true}; {} | bot_response=str({'disconnect': True}) |
| store_page_action | page_name, identifier_slot, callback_identifier | Fernet-encrypt identifier; mint store-page JWT (access_limit regexes); no HTTP | slots user_identifier, temp_token, store_page_name, callback_identifier; no utter; empty identifier re-raises (2 logs); other errors -> empty slots | exception (no bot_response) |
| agent_action | agent_id, dispatch_bot_response | POST {simple_agent.url}/agents/{bot}/{agent_id}/run/{sender}/simple {message, session_id:null, metadata:{}, max_iterations:1}, X-user + Bearer 15-min JWT; non-2xx raises | utters output or str(api_response); fail "I have failed to process your request."; KAR | url, bot_response, api_response, exception |

### Library Landscape
| Concern | Recommendation | Confidence |
|---|---|---|
| Framework | Micronaut 4.x, **bump to >= 4.10.24** (http-client CVE) | high |
| Mongo | `micronaut-mongo-sync` (blocking MongoClient, `mongodb.uri`, `MongoClientSettingsBuilderCustomizer`) [source: https://micronaut-projects.github.io/micronaut-mongodb/latest/guide/]; keep tracker/log/config as `org.bson.Document`/`LinkedHashMap`, not POJO codecs | high / med (Document choice is an inference) |
| POJO serde | `@Serdeable`/`@Introspected` compile-time; `@BsonDiscriminator` needs `mongodb.package-names` [source: https://guides.micronaut.io/micronaut-mongodb-synchronous-gradle-java/] | high |
| Outbound HTTP | low-level Micronaut `HttpClient` with `HttpRequest.create(method, uri)`, since URLs come from the DB at runtime. Declarative `@Client` is a poor fit [source: https://docs.micronaut.io/4.3.7/api/io/micronaut/http/client/annotation/package-summary.html]. Disable auto-follow and write your own redirect loop. Per-request total timeout via `.timeout()`/`orTimeout`. `java.net.http` is an alternative, but it has no filters or tracing. | med |
| Templating | hand-rolled interpolator (~100 lines). Not Jinjava, Pebble or JTE (reflection, wrong grammar) [source: https://central.sonatype.com/artifact/com.hubspot.jinjava/jinjava/] | med-high |
| Pyscript | delegate over HTTP. Avoid GraalPy: binary size, CPython gaps, sandbox risk [source: https://graalvm.org/dev/reference-manual/python/native-applications] | med-high |
| Fernet | hand-roll (~40 lines javax.crypto: `0x80‖ts BE8‖IV16‖AES-128-CBC/PKCS5‖HMAC-SHA256 32`, key = signing 16 + enc 16, urlsafe-b64 padded), or fernet-java8 1.4.2 with the 60s default TTL overridden [source: https://github.com/l0s/fernet-java8]. Verify against the spec vectors [source: https://github.com/fernet/spec] | high (format), med (lib maintenance) |
| JWT | hand-rolled HS256 with `javax.crypto.Mac` (~20 lines): header `typ` then `alg`, compact separators, integer `exp`. Or nimbus via micronaut-security. Avoid jjwt in native [source: https://github.com/jwtk/jjwt/issues/637] | med |
| Email | `micronaut-email-javamail` (Jakarta Mail, ships native hints) [source: https://docs.micronaut.io/5.1.x/email/]; test STARTTLS/SSL + auth | med |
| uuid7 | RFC 9562. Hand-roll ~10 lines (SecureRandom) or `com.github.f4b6a3:uuid-creator` `getTimeOrderedEpoch()`; store as 32-char lowercase hex | high (layout), med (libs) |
| Logging | logstash-logback-encoder to stdout. Avoid Async/RollingFile appenders in native [source: https://mailman.qos.ch/pipermail/logback-dev/2022-November/013193.html] | med |
| Native build | `./gradlew nativeCompile`; tracing agent over the full suite; `@ReflectionConfig`/`@TypeHint` [source: https://guides.micronaut.io/latest/micronaut-graalvm-reflection.html] | high (mechanics), low-med (Mongo driver specifics) |
The library agent noted thin search results and no adoption metrics. The Document-vs-POJO, java.net.http and per-timeout client-cache points are knowledge-based.

### Best Practices
1. **Fixture mining from pytest** (med). Use a `conftest.py` autouse recorder, so no test needs editing. It does the following:
   - Wraps `responses.RequestsMock._on_request` and `aioresponses._request_mock`, and reads `responses.calls`.
   - Wraps `TestClient.post`.
   - Snapshots Mongo before and after, using `bson.json_util` with CANONICAL_JSON_OPTIONS.
   - Writes `fixtures/<nodeid>.json`.
   - Uses `pytest_runtest_makereport` to drop failing tests.

   Freeze time with freezegun or time-machine. vcrpy, pytest-recording and `responses._recorder` record only real traffic, so they do not fit [source: https://libraries.io/pypi/vcrpy]. Size the work first with `pytest --collect-only` against the 434 IDs. Expect some tests to patch Python internals with no Java equivalent. These need to be ported by hand.
2. **Java replay**. A JUnit `@TestFactory` iterates over the fixtures: seed Mongo, configure WireMock stubs, POST, then run three checks:
   - JsonUnit on the response, ignoring `_id`/`timestamp`.
   - The WireMock journal against the recorded hits.
   - The Mongo documents against the after-snapshot.
3. **Test structure** (med). Use an abstract `AbstractActionParityTest` with two subclasses:
   - `InMemoryParityTest`: env `inmem`, MemoryActionCatalog, fast.
   - `MongoParityTest`: env `mongo`, Micronaut Test Resources/Testcontainers, which starts automatically when no `mongodb.uri` is set [source: https://docs.micronaut.io/5.1.x/mongodb/].

   Compare BSON with `Document.toJson(RELAXED)`. Drop collections in `@BeforeEach`, and use separate DB names for parallel runs.
4. **JSON/repr parity** (med-high):
   - Python `json.dumps` uses `", "`/`": "` separators, `ensure_ascii` `\uXXXX` escaping, `1e+16` float formatting and insertion order.
   - Jackson needs custom separators, ESCAPE_NON_ASCII, a custom float serializer (or numeric comparison) and LinkedHashMap with no key sorting.
   - Several log fields hold `str(dict)`. Python repr uses single quotes (double quotes if the string contains `'`), `True/False/None`, `Decimal('1')` and `datetime.datetime(...)`. Build a `PyRepr.of(Object)` helper and unit-test it against captured Python strings.
   - Grep `kairon/actions` for `str()`, `repr()` and f-strings of dicts that are persisted.
5. **Redirect and timeout replication** (med-high). aiohttp behaviour to replicate:
   - `allow_redirects=True`, max 10 hops.
   - 301/302/303 change POST to GET and drop the body. 307/308 keep both.
   - Authorization is stripped cross-origin (verify against the pinned version).
   - `ClientTimeout(total)` is a wall-clock cap that includes connect, redirects and body.

   Replicate this explicitly. TLS verification stays on.

### Existing Art
- **Characterization / golden master**: record the legacy output per input, normalize IDs and times, and investigate every diff before re-recording [source: https://en.wikipedia.org/wiki/Characterization_test] [source: https://dev.to/rnowif/the-blind-golden-master-67h] (high). This is the core strategy.
- **Diffy / Opendiffy**: multicasts each request to candidate, primary and secondary, and subtracts the noise between the two primaries. It only diffs HTTP responses and is blind to Mongo, outbound calls and mail. Replaying non-idempotent POSTs is also a problem [source: https://blog.x.com/engineering/en_us/a/2015/diffy-testing-services-without-writing-tests] (high). Useful only as a later shadow stage.
- **Shadow testing / traffic mirroring** before cutover [source: https://microsoft.github.io/code-with-engineering-playbook/automated-testing/shadow-testing/] (high). "Tap compare" was found by title only [source: https://rednafi.com/system/tap-compare-testing/] (low).
- **WireMock record/playback and request journals**: point both implementations at WireMock and diff the journals [source: https://wiremock.org/docs/record-playback/] (high). **JsonUnit** supports ignore paths and placeholders [source: https://github.com/lukas-krecan/JsonUnit]. JSONassert offers STRICT/LENIENT [source: https://howtodoinjava.com/java/library/jsonassert-tutorial]. No dedicated Mongo diff tool exists, so strip `_id` and times and compare with JsonUnit (med).
- **Rasa protocol**: request `{next_action, sender_id, tracker, domain, version}`, response `{events, responses}`, slot event with explicit `timestamp:null` [source: https://rasa.com/docs/rasa-pro/action-server/actions] [source: https://rasa.com/docs/reference/api/pro/action-server-api/] (high). JRasa is a Java SDK for Rasa 3.x [source: https://github.com/uncle-lv/JRasa] (med). Do not depend on it, because the contract is a single POST that is simple to implement.
- **Python-to-JVM lessons** (low): one write-up ran Java and Python in parallel on live traffic for weeks. Most diffs came from undocumented defaults: empty-array serialization, timeout inheritance and error-message text that clients parse [source: https://agent.kombai.com/kombai-inspiration-library/app-pages/blog-posts/web/65/index.html].

### Pitfalls
1. **Scheduler pickle** (high codebase, med web):
   - What Python writes: `schedule.py:~192-236` builds `job_kwargs {version=1, trigger, executor, func, args, kwargs, id, name="execute_task", misfire_grace_time=7200, coalesce, next_run_time, max_instances=1}`. It inserts `Binary(pickle.dumps(job_kwargs, HIGHEST_PROTOCOL))` into the events DB (`events.queue.name`), collection `events.scheduler.collection`.
   - Who reads it: only the stock APScheduler `MongoDBJobStore` (`events/scheduler/kscheduler.py:9,80-84`). `/api/events/dispatch/{id}` only wakes the scheduler (`kscheduler.py:165-168`).
   - Java could technically write it with `net.razorvine:pickle`, but there is no documented working case. It would break silently on an APScheduler or tz-library upgrade, a corrupt job is deleted silently, and unpickling is an RCE surface [source: https://apscheduler.readthedocs.io/en/3.x/modules/jobstores/mongodb.html].
   - Do not write the pickle from Java.
2. **uuidRepresentation** (med): mongoengine `connect()` defaults to `pythonLegacy` (subtype 3), while Java driver 5.x defaults to UNSPECIFIED and throws. Set `uuidRepresentation=pythonLegacy` and never use JAVA_LEGACY [source: https://www.mongodb.com/docs/languages/python/pymongo-driver/current/data-formats/uuid/]. Verify the subtype on real documents. uuid7 values stored as hex strings are unaffected.
3. **Date truncation** (high): BSON stores int64 milliseconds and PyMongo truncates microseconds. Truncate `Instant.now()` to MILLIS. Write dates through BSON codecs, never as ISO strings or epoch numbers. The `utcnow` values are naive UTC.
4. **Field order** (med): mongoengine writes declared fields in declaration order, then dynamic fields. Use `Document` (a LinkedHashMap) and replicate the order. Check whether `_cls` is present (only with allow_inheritance).
5. **Netty blocking and loopback** (med):
   - Never block the event loop. Use `@ExecuteOn(TaskExecutors.BLOCKING)` with `micronaut.executors.blocking.type=virtual` [source: https://github.com/micronaut-projects/micronaut-core/issues/3694] [source: https://docs.micronaut.io/4.4.8/api/io/micronaut/http/client/netty/BlockHint.html].
   - On JDK 21, virtual threads pin inside `synchronized` (Mongo sync, Jakarta Mail). JEP 491 fixes this in JDK 24+.
   - parallel_action self-loopback needs a blocking pool at least as large as the fan-out, or virtual threads.
   - Defaults to verify (low-med, from memory):

     | Setting | Micronaut | Python side |
     |---|---|---|
     | Server max-request-size | ~10MB | uvicorn unlimited (large trackers may get 413) |
     | Client read-timeout | 10s | 60s action timeout |
     | Idle-timeout | ~5min | uvicorn keep-alive 5s |
     | Max header size | 8KB | |
6. **Native-image gotchas** (med):
   - JCA is fine if algorithm names are string literals [source: https://www.graalvm.org/jdk21/reference-manual/native-image/dynamic-features/JCASecurityServices/].
   - Jakarta Mail needs resource and reflection hints. The typical failure is "no object DCH for MIME type" [source: https://encircle360.com/en/blog/graalvm-native-image-pitfalls].
   - `mongodb+srv` relies on JNDI DNS. Prefer plain `mongodb://h1,h2/?replicaSet=` or add dnsjava.
   - Skip CSFLE.
   - No native config exists yet, although a `build/native` directory shows an attempt.
7. **HTTP wire differences** (med-high, knowledge-based except the UA source):
   - User-Agent: requests sends `python-requests/X` [source: https://www.zenrows.com/blog/python-requests-user-agent] and aiohttp sends `Python/3.x aiohttp/3.x`. Micronaut sends none.
   - Content-Type: Python sends `application/json` without charset. Micronaut may append `; charset=UTF-8`.
   - Form encoding: requests form-encodes a nested dict lossily as `a=b`, repeats keys for lists and drops None. aiohttp raises TypeError on a nested form dict.
   - Query encoding: Python encodes spaces in queries as `+` and keeps `~`. Java URLEncoder escapes `~`, and URI uses `%20`.
   - Header order differs.
   - Pin whatever downstream services might inspect.
8. **Micronaut http-client CVE**, GHSA-q6gh-6v2r-hjv3 (high): in versions 4.x below 4.10.24, `DefaultHttpClient` forwards Authorization, Cookie and Proxy-Authorization across domains on redirect, with no hop cap [source: https://advisories.gitlab.com/maven/io.micronaut/micronaut-http-client/GHSA-q6gh-6v2r-hjv3/]. `action-server/build.gradle:38` and `gradle.properties:3` pin **4.10.22**, which is vulnerable. Bump it, and own the redirect loop.
9. **Fernet TTL** (high): fernet-java8 applies a 60s TTL by default, while Python `Fernet.decrypt` has no TTL unless `ttl=` is passed (confirm in `shared/utils.py:1391-1407`).

## Contradictions & Open Questions
1. RESOLVED: the `server.py` webhook line numbers differ between agents (~277-295 vs 315-333). This is line drift. It is the same function, around 315-333.
2. RESOLVED: pyscript and the expression evaluator are always remote (HTTP or Lambda). The LLM call in `prompt_action` (litellm), the Qdrant query and CognitionSchema reads are in process in Python. The Java port delegates them to `llm-url`/`vector-url`, which is a behavioural divergence for prompt/database actions.
3. RESOLVED: `utter_message(None)` produces the 8-key dict with `text:null`. `next_action` is case-sensitive. Collection names are the mongoengine defaults.
4. RESOLVED: no generic JSON scheduling endpoint exists. `/api/events/execute/{event_type}?is_scheduled=true` (`events/server.py:124-132`, `models.py:25-40`) allows only `message_broadcast` and `analytics_pipeline`. Commit 8032de5c did not change who writes jobs. The direct pickle insert still conflicts with the stated "event server is only source of truth" rule.
5. UNRESOLVED (found in synthesis, verified in code): the Java `WebhookTest.missingTrackerIs422` and `emptyBodyIs422` assert **HTTP status 422** with a `{success,error_code,message,data}` body. Python returns:
   - HTTP 500 for a missing `tracker` (KeyError in `handlers/action.py:19`, no handler).
   - HTTP 200 with `error_code:422` for validation errors (`server.py:185-192`). No `JSONResponse` in `server.py` sets a status code.

   **Decision:** match Python exactly (500 / 200), or keep the Java behaviour as an intentional deviation?
6. **Decision, schedule_action:** pick one of the following:
   - (a) Add a JSON scheduling endpoint to the Python events server and have Java call it. This is recommended, and it aligns with 8032de5c.
   - (b) Run a Python sidecar or an outbox collection that Python polls.
   - (c) Defer `schedule_action` from v1 and keep routing it to Python.
   - (d) Write the pickle from Java. This is rejected.
7. **Decision:** are `prompt_action` and `database_action` in v1 scope? Their in-process LLMProcessor, Qdrant and CognitionSchema dependencies, the hidden openrouter switch via `Sysadmin.get_llm_secret`, and the cwd-relative `./template/rephrase-prompt.txt` used by `kairon_bot_response` rephrase make this a large separate scope.
8. **Decision:** port the failure mail to `support_mail` (SMTP side effect, part of the chosen parity bar) or log only?
9. **Decision:** is a native image a hard requirement? Nothing is configured yet, and Mongo, Jackson and Jakarta Mail are untested under native.
10. **Decision:** fixture strategy. Auto-mine the 434 Python tests with the conftest recorder (recommended), port them by hand, or use a hybrid.
11. **Decision:** should Java honour `DATABASE_URL` and default to the `kairon` DB, as Python does? See the config drift section.
12. OPEN (verify): the `uuidRepresentation` binary subtype on real documents; whether `mongodb+srv` is used; whether the Kairon Rasa version sends `domain_digest` without `domain`; whether downstream services inspect UA, charset or query encoding (capture with WireMock or mitmproxy); the Micronaut 4.10 defaults; whether Python passes `ttl=` to Fernet; the exact body of `encrypt_secrets` (`utils.py:146-160`) and the media multipart path (`utils.py:162-232`); `LLMProcessor.predict` internals; and the PyJWT header and claims.
13. OPEN: the Python pyscript URL key is `async_callback_action.pyscript.url`, while the trigger flag is `evaluator.pyscript.trigger_task`. This mixed-namespace inconsistency should be mirrored as-is, not "fixed".

## Codebase Context
- **Java port inventory** (`action-server/`, Micronaut plugin 4.5.4, Micronaut 4.10.22, Java 21, mongodb-driver-sync 5.5.1, serde-jackson):
  - All 24 types are mapped 1:1 to `kairon/shared/actions/models.py:32-56`. `ActionFactory.java:21-47` mirrors the Python resolution order.
  - Catalog: an `ActionCatalog` interface with `MongoActionCatalog` (`@Requires(kairon.action.catalog=mongo)`, findActive/findBotSettings/findByBot/insert) and `MemoryActionCatalog`.
  - Runtime: Dispatcher, TrackerState, ActionContext, ActionProcessor and WebhookController.
  - Support: `ActionSupport` (666 LOC), `HttpCaller` (266, with a test-only `https-stub-base` rewrite at line 212), `Tokens` (261, Fernet + JWT), Jsons and Maps.
  - Status by action: fully complete and tested are http, slot_set, two_stage, bot_response, live_agent, callback, schedule, parallel, voice_call, voice_disconnect and store_page. "Looks complete", untested or thinly tested, are form_validation, email, google, jira, zendesk, pipedrive, hubspot, razorpay, prompt, pyscript, database, web_search and agent.
  - Confidence is high on structure and medium on per-action fidelity.
  - The Java `ScheduleAction` exists and has one test. How it writes the job (pickle or otherwise) must be audited against open question 6.
- **Parity harness**: `ParityKit.java` (482 LOC) runs an in-JVM `com.sun.net.httpserver` stub on 127.0.0.1:18780.
  - It records every request as a `Hit`, with canned responses via PATH_BODIES/PATH_STATUS/SCRIPT_BODIES/forcedStatus/bodyOverride.
  - It uses MemoryActionCatalog and reads logs from `Kairon.LOGS`. There is no real Mongo.
  - `WebhookTest.java` (496 LOC) has about 22 tests, and `application-test.yml` points all URLs at the stub.
  - The harness can already assert responses, logs and outbound hits. It has no recorded fixtures and no record-and-compare.
- **`python-action-nodes.txt`** (`action-server/src/test/resources/`): 434 pytest node IDs, broken down as follows. No code reads the file. It is an unwired checklist, and current coverage is about 22 of 434.

  | Test file | Nodes |
  |---|---|
  | action_test.py | 210 |
  | action_service_test.py | 164 |
  | test_voice_call_action.py | 20 |
  | test_agent_action.py | 19 |
  | test_store_page_action.py | 16 |
  | kremote_action_test.py | 5 |
- **Python test assets**:
  - `tests/integration_test/action_service_test.py` (16,560 lines, ~165 tests) uses TestClient against `kairon.actions.server:action` with **real Mongo** (`connect` at line 70, not mongomock). It mocks with `responses` (55 uses), `aioresponses`, `patch`/`AsyncMock` and `deepdiff`.
  - `tests/unit_test/action/action_test.py` has 5,484 lines and ~211 tests.
  - Each integration test is a fixture candidate: seed documents, request, mocked upstream, expected JSON.
- **Config key drift (Python -> Java)**:
  | Concern | Python | Java |
  |---|---|---|
  | Mongo | `database.url` / env `DATABASE_URL`, default `mongodb://mongo:27017/kairon` | `mongodb.uri` / `MONGODB_URI`, default `mongodb://localhost:27017/conversations` (env name AND DB differ) |
  | Pyscript | `async_callback_action.pyscript.url` + `evaluator.pyscript.trigger_task` (Lambda) | `kairon.action.pyscript-url` (no Lambda path) |
  | Evaluator | `evaluator.url` | `kairon.action.evaluator-url` |
  | Timeout | `action.request_timeout` (60; code default 1) | `kairon.action.request-timeout` |
  | Callback / events / live agent / LLM / vector / agent / web search | `async_callback_action.url`, `events.server_url`, `live_agent.*`, `llm.*`, `vector.*`, `simple_agent.url`, `web_search.{url,trigger_task}` | `callback-base-url`, `events-server-url`, `live-agent-{url,token,enabled}`, `llm-url`, `vector-url`, `simple-agent-url`, `web-search-url` (no Lambda) |
  | Secrets | `security.fernet_key`, `security.secret_key`, `async_callback_action.short_secret` | `fernet-key`, `jwt-secret`, `jwt-algorithm`, `token-expire` (short_secret mapping not confirmed) |
  | Other | `support_mail`, email config, `cors.origin` | no support-mail key seen; CORS GET/POST/OPTIONS any origin (Python allows all methods + credentials) |
  Lambda trigger paths (pyscript, web_search) have no Java equivalent.
- **docker-compose** (`docker/docker-compose.yml:77-95`): the `kairon-action-server` service runs the Python image (`uvicorn kairon.actions.server:action --port 5055`) with `DATABASE_URL` set. Consumers reach it at `ACTION_SERVER_URL: http://kairon-action-server:5055/webhook` (line 40). There is no Java Dockerfile or service yet. A drop-in replacement needs the same service name and port, and must accept `DATABASE_URL`.
- The `kairon-action/` Rust prototype is deleted in the working tree. It is not part of this scope.

## Implications for Design
1. **Character-exact surfaces** (must be golden-tested):
   - The webhook JSON, including the 8-key message dict, `timestamp:null` and slot insertion order.
   - The error contract: 200-with-empty-events, `null`, and the 200/`error_code` envelopes.
   - Every fallback utterance string.
   - The templating grammar and replacement order.
   - `json.dumps` output embedded in strings (`${RESPONSE}`, dict values).
   - `str(dict)` repr fields (`bot_response` in two_stage, bot_response and voice_disconnect).
   - Log messages such as "Setting slot 'x' to 'y'.".
   - The `action_server_logs` field set and order per type, including `trigger_info` defaults and the typeless processor-failure record.
   - The outbound request method, URL, body and auth for each integration.
2. **Semantics that must match (not byte-exact)**:
   - Swallowed transport errors (`status=None`) and the OK set {200,201,202,204}.
   - Effectively no retry, and a total wall-clock timeout.
   - The aiohttp redirect rules.
   - Per-slot independent failure in `fill_slots_from_response`.
   - Parallel last-write-wins slot merge with discarded child utterances.
   - The double log on the store_page empty-identifier path.
   - Fire-and-forget failure mail.
   - uuid7 hex, millisecond dates, pythonLegacy UUIDs.
3. **Needs a decision before kits**: open questions 5-11. The schedule_action and prompt/database scope decisions change the domain count.
4. **Defer candidates**:
   - Native image.
   - Lambda trigger paths.
   - Shadow or Diffy traffic mirroring, as a post-v1 cutover stage.
   - `kairon_bot_response` LLM rephrase.
   - Media multipart upload in http_action, until `utils.py:162-232` has been read.
5. **Immediate fixes, independent of design**:
   - Bump Micronaut to >= 4.10.24.
   - Add `DATABASE_URL` support.
   - Set `uuidRepresentation=pythonLegacy`.
   - Do not import the `system.yaml` default secrets.
6. **Candidate domain decomposition for kits (recommended, A)**:
   1. `webhook-contract`: request parsing, tracker, response envelope, error contract, middleware/headers, health endpoints.
   2. `dispatch-and-logging`: type resolution, processor catch-all, ActionServerLogs schema per type, request_id, trigger_info, failure mail.
   3. `templating-and-params`: prepare_url, prepare_response, get_parameter_value, keyvault/Fernet, PyRepr, json.dumps parity.
   4. `outbound-http`: async/sync clients, swallow vs raise semantics, timeouts, redirects, wire format, evaluator and pyscript delegation.
   5. `simple-actions`: slot_set, form_validation, two_stage, bot_response (without rephrase), voice_disconnect, store_page, callback.
   6. `integration-actions`: http, email, google, web_search, jira, zendesk, pipedrive, hubspot, razorpay, live_agent, agent, voice_call, pyscript.
   7. `orchestration-actions`: parallel (loopback), schedule (depends on decision 6).
   8. `llm-actions`: prompt, database (if in scope).
   9. `parity-harness`: Python conftest recorder, fixture format, Java replay (in-memory + Testcontainers), WireMock journal and Mongo diff.
   10. `config-and-deploy`: config key mapping, docker-compose service swap, optional native.

   Tradeoff: clean cross-cutting layers, but the action kits depend on 3 and 4 landing first.
7. **Alternative B, per-action vertical kits** (24 kits plus a shared-core kit). Fixtures map 1:1 to kits, which gives easy progress tracking against the 434 nodes. The risk is cross-cutting drift: templating and logging get re-specified in each kit.
8. **Alternative C, harness-first, then risk tiers**:
   - Kit 1 is the recorder plus replay.
   - Tier 1 covers the exact contract and the top-traffic actions (http, slot_set, bot_response, form_validation).
   - Tier 2 covers the integrations.
   - Tier 3 covers the risky ones: parallel, schedule, prompt, database.

   Fastest path to a measurable parity percentage, but the kits are organized by risk rather than by domain, so their boundaries are less clean.

## Sources
**Web**
- https://micronaut-projects.github.io/micronaut-mongodb/latest/guide/
- https://guides.micronaut.io/micronaut-mongodb-synchronous-gradle-java/
- https://guides.micronaut.io/latest/micronaut-graalvm-reflection.html
- https://docs.micronaut.io/4.3.7/api/io/micronaut/http/client/annotation/package-summary.html
- https://docs.micronaut.io/latest/api/io/micronaut/http/client/HttpClientConfiguration
- https://docs.micronaut.io/5.1.x/email/
- https://docs.micronaut.io/5.1.x/mongodb/
- https://docs.micronaut.io/4.4.8/api/io/micronaut/http/client/netty/BlockHint.html
- https://github.com/micronaut-projects/micronaut-core/issues/3694
- https://advisories.gitlab.com/maven/io.micronaut/micronaut-http-client/GHSA-q6gh-6v2r-hjv3/
- https://central.sonatype.com/artifact/com.hubspot.jinjava/jinjava/
- https://graalvm.org/dev/reference-manual/python/native-applications
- https://www.graalvm.org/jdk21/reference-manual/native-image/dynamic-features/JCASecurityServices/
- https://encircle360.com/en/blog/graalvm-native-image-pitfalls
- https://mailman.qos.ch/pipermail/logback-dev/2022-November/013193.html
- https://github.com/l0s/fernet-java8
- https://github.com/fernet/spec
- https://github.com/jwtk/jjwt/issues/637
- https://libraries.io/pypi/vcrpy
- https://apscheduler.readthedocs.io/en/3.x/modules/jobstores/mongodb.html
- https://www.mongodb.com/docs/languages/python/pymongo-driver/current/data-formats/uuid/
- https://www.zenrows.com/blog/python-requests-user-agent
- https://en.wikipedia.org/wiki/Characterization_test
- https://dev.to/rnowif/the-blind-golden-master-67h
- https://blog.x.com/engineering/en_us/a/2015/diffy-testing-services-without-writing-tests
- https://microsoft.github.io/code-with-engineering-playbook/automated-testing/shadow-testing/
- https://rednafi.com/system/tap-compare-testing/
- https://rasa.com/docs/rasa-pro/action-server/actions
- https://rasa.com/docs/reference/api/pro/action-server-api/
- https://github.com/uncle-lv/JRasa
- https://agent.kombai.com/kombai-inspiration-library/app-pages/blog-posts/web/65/index.html
- https://wiremock.org/docs/record-playback/
- https://github.com/lukas-krecan/JsonUnit
- https://howtodoinjava.com/java/library/jsonassert-tutorial

**Repo files (key)**
- `kairon/actions/server.py`, `kairon/actions/handlers/action.py`, `kairon/actions/handlers/processor.py`, `kairon/actions/definitions/{factory,base,http,set_slot,form_validation,email,google,web_search,jira,zendesk,pipedrive,hubspot,razorpay,prompt,pyscript,database,live_agent,callback_action,schedule,custom_parallel_actions,two_stage_fallback,bot_response,voice_call,voice_disconnect,store_page,agent_action}.py`
- `kairon/shared/actions/{utils,data_objects,models}.py`, `kairon/shared/utils.py`, `kairon/shared/rest_client.py`, `kairon/shared/middleware.py`, `kairon/shared/data/{data_objects,constant}.py`, `kairon/shared/callback/data_objects.py`, `kairon/shared/live_agent/live_agent.py`
- `kairon/events/server.py`, `kairon/events/scheduler/kscheduler.py`, `kairon/events/models.py`, `kairon/events/utility.py`; commit 8032de5c
- `.venv/lib/python3.12/site-packages/rasa_sdk/{executor,events,interfaces}.py`
- `system.yaml`, `docker/docker-compose.yml`
- `tests/integration_test/action_service_test.py`, `tests/unit_test/action/{action_test,test_agent_action,test_store_page_action,test_voice_call_action,kremote_action_test}.py`
- `action-server/build.gradle`, `action-server/gradle.properties`, `action-server/src/main/resources/application.yml`, `action-server/src/test/resources/{application-test.yml,python-action-nodes.txt}`, `action-server/.../actions/ActionFactory.java`, `ParityKit.java`, `WebhookTest.java`
