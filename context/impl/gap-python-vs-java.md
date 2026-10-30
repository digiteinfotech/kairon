---
created: "2026-10-27"
last_edited: "2026-10-27"
---

# Gap: Python `kairon.actions` vs Java `action-server`

Source: 4 read-only agent passes (core/http, integrations, orchestration, server/infra), 2026-10-27. Baseline: full Python parity, so deferred and kit-excluded items are listed and tagged.
Only C1's write side was re-verified by the orchestrator (`data_objects.py:291`, `CallbackAction.java:89`, `MongoActionCatalog.java:80-82`). Everything else is agent-reported with file:line and not independently re-checked. Nothing was run.
Java paths are relative to `action-server/src/main/java/com/kairon/action/`. `utils.py` is `kairon/shared/actions/utils.py`.
"known F-nnn" refers to `impl-review-findings.md`.

## Priority gaps

| # | Sev | Gap | Python | Java | Status |
|---|-----|-----|--------|------|--------|
| 1 | P1 | callback_data written with BSON Date `timestamp`; Python field is `FloatField`. `validate_entry` does `timestamp + expire_in`, so a Java-minted callback may fail on load or never expire. Java also omits `state` and `execution_mode`. Crash-on-load is unverified (needs a mongoengine run). | callback/data_objects.py:291, 280-304, 359 | CallbackAction.java:67-89; MongoActionCatalog.java:80-82 | NEW |
| 2 | P1 | `${a.b}` placeholder with a missing dict key: Python raises ActionFailure, Java yields the string "None" and continues. | utils.py:620-628 | support/ActionSupport.java:875-891, 589-594 | NEW |
| 3 | P1 | prompt_action and database_action deferred. Both fail with "<type> type action is not supported with action server". | factory.py:44,51 | actions/ActionFactory.java:22-33 | Deliberate scope; P1 for any bot using them |
| 4 | P1 | intent() skip-fallback semantics (also hits parallel_action) | processor.py:30,44 | runtime/TrackerState.java:78-87 | known F-004 |
| 5 | P1 | Non-2xx handling / media source / mask strategy | utils.py:45-87, 185-231, 2020 | HttpCaller.java:101; ActionSupport.java:776-812, 328 | known F-003, F-002, F-001 |
| 6 | P2 | schedule `runAt` accepts ISO/space formats only. Python uses `dateutil.parser.parse` ("27 Oct 2026 10:00", "10/27/2026"). | schedule.py:110,125 | ScheduleAction.java:166-189 | NEW |
| 7 | P2 | No lambda path for pyscript (`PYSCRIPT_TRIGGER_TASK`) or web_search (`trigger_task`) | utils.py:760-769, 577-583 | ActionSupport.java:450-466; WebSearchAction.java:78 | NEW (Lambda is kit-excluded) |
| 8 | P2 | Unknown route / wrong method: Python returns HTTP 200 `{success:false,error_code:404/405}`. Java returns the Micronaut default 404/405. | server.py:140-150 | server/WebhookController.java (no handler) | NEW |
| 9 | P2 | Mongo/JWT/AppException/mongoengine errors in the catch-all: Python returns 200 `{success:false,error_code:422}`. Java returns 500 text/plain. | server.py:163-290; processor.py:41-53 | WebhookController.java:104-108; ActionProcessor.java:96-100 | NEW |
| 10 | P2 | Text dispatch uses `String.valueOf` instead of `str()` (dict, bool, None render differently). JSON list/scalar response goes out as text; Python sends a custom payload. | utils.py:688-716 | ActionSupport.java:653-669 | NEW |
| 11 | P2 | form_validation: "Expression evaluation log" `messages[]` entry never written | form_validation.py:69-70 | FormValidationAction.java:59-60 | NEW |
| 12 | P2 | two_stage_fallback takes the first training example; Python takes the newest (`-timestamp`) | processor.py:2900-2902 | TwoStageFallbackAction.java:106-117 | NEW |
| 13 | P2 | razorpay: `short_url` missing or non-dict body stays Success in Java, Fail plus mail in Python. `api_response` is "None" on failure in Python, absent in Java. | razorpay.py:91,119 | RazorpayAction.java:73,89 | NEW |
| 14 | P2 | `api_response` logged with Java `toString` instead of Python repr, and `""` kept instead of None (hubspot, agent_action) | hubspot.py:91; agent_action.py:125 | HubspotAction.java:67; AgentAction.java:81 | NEW |
| 15 | P2 | jira: Python does `GET project`/`GET issuetype` and sends ids; Java sends key/name in one POST. Unknown project/type fails differently. | utils.py:918-966 | JiraAction.java:43-55 | NEW |
| 16 | P2 | pipedrive: Java rewrites the domain (appends `.pipedrive.com`, forces https, drops the path); Python uses the raw domain | pipedrive/client.py:48-51 | PipedriveAction.java:46, 97-112 | NEW |
| 17 | P2 | google_search with no api_key: Python scrapes via `googlesearch`, Java fails | utils.py:549-558 | GoogleSearchAction.java:53-57 | NEW (kit-excluded) |
| 18 | P2 | bot_response `rephrase_response` (LLM) missing | bot_response.py:153-157 | BotResponseAction.java:93-105 | NEW (kit-excluded) |
| 19 | P2 | parallel_action: 60s budget vs Python 300s; no recursion guard | custom_parallel_actions.py:152-171 | ParallelAction.java:158-175 | known F-014 |
| 20 | P2 | Other known: decryptMaybe, replaceOne vs $set, CORS echo, sender-id decrypt, next_action strip, body limit, compose secrets, test stub in prod | n/a | n/a | known F-006, F-015, F-012, F-009, F-007, F-013, F-016, F-010 |

## P3 / minor (all NEW unless noted)

**Logged-field and message text**
- http_action: `bot_response` logged as "" or "{}" when falsy (Python logs None); a non-dict `dynamic_params` result is tolerated (Python fails); a falsy non-list `media_ids` skips the media path. `http.py:116-119,186`.
- set_slot: log text interpolates `true`/`null` instead of `True`/`None`. `set_slot.py:62`.
- Error texts embed Java `Map.toString()` instead of Python repr (evaluator, pyscript, web-search). `utils.py:587,1096`.
- form_validation: Python's failure log has no `exception` field, Java adds one. "Expression evaluation result" prints `true` instead of `True`.
- email: invalid-type check order is reversed (Python checks to_email first). `email.py:126-130`.
- razorpay: "Got null." vs "Got None.". `razorpay.py:75,97`.
- live_agent: unmapped-channel error text lacks KeyError quotes. A non-200 response is a different message (known F-003). `live_agent.py:81`.
- voice_call: `ChannelLogs` insert lacks `errors: []`. Twilio/Exotel failure text is hand-emulated. `voice_call.py:79-87`.
- google_search: missing title/snippet/link renders "null" (Python KeyError); the HttpError text differs. `utils.py:562-566`.
- agent_action: non-dict body uses Java `String.valueOf`. `agent_action.py:~103`.

**pyscript**
- `dispatch` is set before context build, so Java utters the failure text where Python does not. `pyscript.py:70-71,87-89`.
- 60s budget plus a `timestamp` header, where Python has `timeout=None`. `utils.py:1786-1808`.
- A non-dict body is accepted. The logged config keeps `_id`. `pyscript.py:41,73-76`.

**Callback**
- `expire_in`/`shorten_token` default is not applied (Python default 0). `data_objects.py:116,195-200`.
- A null `dynamic_url_slot_name` is skipped. `callback_action.py:206-209`.

**Schedule**
- Error text prefix differs. An unknown `schedule_action_type` raises a different exception. `schedule.py:117-133,218-219`.

**Shared**
- `attach_response` tolerates a missing `data` key (Python KeyError). `utils.py:641-642`.

**Zendesk**
- Java always sends `tags: null`. `zendesk` data_objects.py:~711.

**Pipedrive**
- Non-ok and non-JSON error text differs. `utils.py:1020-1070`.

**Multiple matches**
- `MultipleObjectsReturned` is lost in two places. Java takes `.first()`. `utils.py:530`; `form_validation.py:60`.

**Server**
- No per-request log line (`rid=... completed_in=...`) and no request-id MDC. `server.py:122-135`.
- No startup Mongo check or `load_system_properties` seeding. `server.py:96-101`.
- No APM/OTel (`instrument_fastapi`).
- Gzip may also compress for deflate/br (unverified).
- No Dockerfile HEALTHCHECK (compose has none for any service).

## Config keys Python reads that Java does not

- `events.scheduler.min_trigger_interval`
- `events.scheduler.collection` and `events.queue.name` (now moot after T-049)
- `web_search.trigger_task` and `evaluator.pyscript.trigger_task` (Lambda)
- `model.agent.url` / `AGENT_URL`. Java has only `SIMPLE_AGENT_URL`. Python usage not traced, so agent_action may use the wrong endpoint. Verify.
- `voice.exotel.subdomain`. Hard-coded at `VoiceCallAction.java:29`.
- `storage.assets.{bucket,root_dir,allowed_extensions}`
- `app.server_url`
- `notifications.{enable,server_endpoint}`
- `lock_store.url`
- `model.retention`
- `apm.enable`

## No gaps found

store_page_action, voice_disconnect, agent_action integration token. Also matching: GET `/`, `/healthcheck` and POST `/webhook` shapes, secure headers, request-id echo, validation-error body, the `action_server_logs` failure shape and field order, `TriggerInfo` defaults, the failure-mail path, the email SMTP flow, and slot-reset semantics.

## Stale tracking

- F-008 (legacy failure-mail shape) is fixed for ParallelAction (`:80`), EmailAction (`:77`) and RazorpayAction (`:86`). `impl-review-findings.md` still lists it for those files.
- F-005 (schedule direct DB write) is resolved by T-049 (commit 63aee133).

## Suggested next steps

1. Verify C1 by loading a Java-written callback_data doc through mongoengine, then fix the timestamp type and add `state` and `execution_mode`.
2. Fix #2 (placeholder missing-key failure) and #8/#9 (404/405 and 422 error envelopes). They are cheap and parity-visible.
3. Decide on #6 (dateutil) and #15/#16 (jira, pipedrive). Port, or record them as deliberate divergences in the kits.
4. Decide whether the lambda path, keyless google, rephrase, prompt and database actions stay out of scope. That is a product call.
