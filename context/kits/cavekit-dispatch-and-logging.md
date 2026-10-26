---
created: "2026-10-26T12:44:00Z"
last_edited: "2026-10-26T14:00:00Z"
---

# Cavekit: Dispatch and Logging

## Scope
Resolving `next_action` to an action type, executing it, the catch-all failure path, the `action_server_logs` record contract (base and per-type fields) and the support failure mail. Action-specific behaviour lives in the action kits.

See context/refs/research-brief-java-action-server-port.md for evidence.

## Requirements

### R1: Action type resolution
**Description:** The action type is resolved in the same order as the Python server, with case-sensitive lookup.
**Acceptance Criteria:**
- [ ] `next_action` = `kairon_voice_disconnect` resolves to type `kairon_voice_disconnect` with no Mongo lookup
- [ ] A `next_action` starting with `utter_` resolves to type `kairon_bot_response`
- [ ] Any other name resolves via the `actions` collection by `bot`, `name` and `status: true`
- [ ] [GAP] `next_action` is stripped of surrounding whitespace but never lowercased: `My_Action` does not match a stored `my_action`
- [ ] A name with no active `actions` document fails with `No action found for given bot and name`
- [ ] [GAP] A resolved type outside the 22 in-scope types fails with `<type> type action is not supported with action server` (with `<type>` replaced)
- [ ] Both failures above follow the catch-all path in R3
**Dependencies:** cavekit-webhook-contract.md R1

### R2: Bot slot mandatory
**Description:** An action cannot run without a bot id and action name.
**Acceptance Criteria:**
- [ ] A tracker whose `bot` slot is missing, null or empty fails with `Bot id and action name not found in slot`
- [ ] That failure follows the catch-all path in R3
**Dependencies:** cavekit-webhook-contract.md R1

### R3: Catch-all failure path
**Description:** Any exception escaping an action is absorbed: a typeless Failed log is written, the failure mail fires, and the webhook returns empty events.
**Acceptance Criteria:**
- [ ] The response is HTTP 200 with `events: []` and `responses` = the messages uttered before the failure (usually `[]`, since actions catch their own errors before uttering)
- [ ] Exactly one new `action_server_logs` document is written by this path
- [ ] That document has no `type` field
- [ ] [GAP] That document contains `intent`, `action`, `sender`, `exception` (the exception text), `bot`, `request_id`, `timestamp`, `status: "Failed"` and `trigger_info`
- [ ] [GAP] The log `intent` (catch-all and every action) is the top entry of `latest_message.intent_ranking` WITHOUT skipping `nlu_fallback`, and null when `intent_ranking` is absent or empty
- [ ] [GAP] `trigger_info` equals `{"trigger_name":"","trigger_type":"implicit","trigger_id":""}` when the request carried none
- [ ] [GAP] One failure mail is attempted (R6)
- [ ] No exception propagates to the HTTP layer
**Dependencies:** cavekit-webhook-contract.md R3

### R4: Base log record
**Description:** Every action log record in `action_server_logs` carries the base fields with the same names, defaults and order as the Python document.
**Acceptance Criteria:**
- [ ] Records are written to the collection named `action_server_logs`
- [ ] `intent` is the latest message's intent name, including fallback intents
- [ ] `sender` is the tracker sender id
- [ ] `user_msg` is the latest message text
- [ ] [GAP] `trigger_info` equals the request `trigger_info` when present, else `{"trigger_name":"","trigger_type":"implicit","trigger_id":""}`
- [ ] [GAP] `request_id` equals the response `X-Kairon-Request-ID` value
- [ ] `bot` is the tracker `bot` slot value
- [ ] `timestamp` is a BSON date in UTC truncated to millisecond precision
- [ ] `status` is `Success` or `Failed`; no other value is written by actions
- [ ] [GAP] Declared fields appear in the order `type, intent, action, sender, headers, url, request_method, request_params, api_response, bot_response, exception, messages, bot, timestamp, status, trigger_info, request_id`, followed by dynamic fields, matching the recorded Python documents
**Dependencies:** cavekit-webhook-contract.md R4, cavekit-config-and-deploy.md R3

### R5: Per-type log fields
**Description:** Each action type writes `type` equal to its type name and the additional fields below (beyond the R4 base). Field values equal the recorded Python values after normalization.
**Acceptance Criteria:**
- [ ] [GAP] For every in-scope type, a Success log contains `type` and every field listed for it in the table
- [ ] [GAP] For every in-scope type, the field set of each recorded fixture's log equals the Python record's field set
- [ ] [GAP] http_action `events[]` contains sub-documents with `type` values `slots`, `response`, `api_call`, `dynamic_params` or `params_list`, and `filled_slots`, in the recorded order
- [ ] [GAP] The http_action `api_call` sub-document contains masked `headers`, `method`, `url`, `payload`, `response`, `status_code`, `time_elapsed`, `response_headers`
- [ ] [GAP] The http_action `filled_slots` sub-document contains `data`, `slot_eval_log`, `time_elapsed`
- [ ] parallel_action writes an empty record before fan-out and later fills it (cavekit-orchestration-actions.md R1)

| Type | Additional log fields |
|---|---|
| http_action | action, url, request_method, bot_response, fail_reason, exception, http_status_code, time_elapsed, events[] |
| slot_set_action | action, messages[] |
| form_validation_action | action (= tracker followup_action), messages[] |
| email_action | action, bot_response, exception |
| google_search_action | action, google_response, bot_response, exception |
| web_search_action | public_search_action_response, bot_response, exception |
| jira_action | action, bot_response, exception |
| zendesk_action | action, bot_response, exception |
| pipedrive_leads_action | bot_response, exception |
| hubspot_forms_action | request_params, api_response, bot_response, exception |
| razorpay_action | request, api_response, bot_response, exception |
| pyscript_action | config, bot_response, messages[], exception |
| live_agent_action | bot_response, messages[], exception |
| callback_action | callback_url, callback_url_slot, identifier, metadata[], bot_response, messages, exception |
| schedule_action | schedule_action, schedule_time, timezone, execution_info, data, bot_response, messages, exception |
| parallel_action | action, sender, bot_response, exception, user_msg, trigger_info, request_id (filled into pre-created empty record) |
| two_stage_fallback | bot_response (Python repr of recommendations), exception |
| kairon_bot_response | enable_rephrasing, is_rephrased, raw_gpt_response, bot_response (Python repr of dict), exception |
| voice_call_action | bot_response, exception |
| kairon_voice_disconnect | bot_response = `{'disconnect': True}` |
| store_page_action | exception (no bot_response) |
| agent_action | url, bot_response, api_response, exception |
| prompt_action | deferred |
| database_action | deferred |

**Dependencies:** R4, cavekit-templating-and-secrets.md R7

### R6: Failure mail
**Description:** A best-effort mail goes to the configured support address on two kinds of failure path: the catch-all (R3) and every in-action exception handler that writes a Failed log. It never affects the response or the log.
**Acceptance Criteria:**
- [ ] [GAP] A catch-all failure (R3) causes one SMTP message to the configured support address
- [ ] [GAP] An in-action failure that writes a Failed log and returns 200 with the action's fallback utterance (for example http_action with an unreachable upstream) causes exactly one SMTP message
- [ ] These Failed paths send no mail of their own: form_validation on a validation miss, slot_set, two_stage_fallback, store_page (store_page reaches the mail only through the catch-all)
- [ ] [GAP] A request that fails once produces exactly one mail, never two
- [ ] [GAP] The mail body contains the action name, bot, exception text, stack trace, slot values and latest user text
- [ ] When SMTP is unreachable, the webhook response and log record are identical to the case where SMTP succeeds
- [ ] [GAP] The webhook response is returned without waiting for the mail send to complete
- [ ] [GAP] Mail template and wording match the Python mail (needs human review)
**Dependencies:** cavekit-outbound-clients.md R7, cavekit-config-and-deploy.md R1

### R7: Double-log on store_page empty identifier
**Description:** The store_page empty-identifier path writes two records, as Python does.
**Acceptance Criteria:**
- [ ] A store_page_action request with an empty identifier slot writes exactly two `action_server_logs` documents
- [ ] One has `type: "store_page_action"` and `status: "Failed"`
- [ ] The other has no `type` field and `status: "Failed"`
- [ ] The response is HTTP 200 with `events: []` and `responses: []` (store_page utters nothing before re-raising)
**Dependencies:** R3 (the action-side record is specified in cavekit-core-actions.md R6)

## Out of Scope
- Templating and parameter resolution (cavekit-templating-and-secrets.md)
- Outbound transport behaviour (cavekit-outbound-clients.md)
- Action implementations (cavekit-core-actions.md, cavekit-integration-actions.md, cavekit-orchestration-actions.md)
- Log fields of prompt_action and database_action (deferred)
- Lambda transports, LLM rephrase, native image
- Status values `Partial_Success` and `PASSED` (unused by actions)

## Cross-References
- See also: cavekit-webhook-contract.md
- See also: cavekit-templating-and-secrets.md
- See also: cavekit-outbound-clients.md
- See also: cavekit-core-actions.md
- See also: cavekit-integration-actions.md
- See also: cavekit-orchestration-actions.md
- See also: cavekit-parity-harness.md
- See also: cavekit-config-and-deploy.md

## Source Traceability
- R1: kairon/shared/actions/utils.py:507-532; kairon/actions/definitions/factory.py:30-58,68-73; kairon/shared/actions/models.py:32-56; kairon/shared/actions/data_objects.py:297-298
- R2: kairon/shared/actions/utils.py (bot slot check)
- R3: kairon/actions/handlers/processor.py:34-48; kairon/actions/handlers/action.py:33
- R4: kairon/shared/actions/data_objects.py:263-282; kairon/shared/data/constant.py:114-118; kairon/shared/middleware.py
- R5: kairon/actions/definitions/*.py (finally blocks); see context/refs/research-java-action-server-port/raw-codebase-patterns.md per-action table
- R6: kairon/shared/actions/utils.py:1140-1156
- R7: kairon/actions/definitions/store_page.py:69-71; kairon/actions/handlers/processor.py:34-48

## Gap Summary
Brownfield verification against the existing port (2026-10-26): 25 met, 20 gaps, 0 unverified by code reading.
Criteria prefixed `[GAP]` are not satisfied by the current code; `[UNVERIFIED]` need runtime, fixture, or human confirmation.

| Req | Gap | Evidence |
|---|---|---|
| R1 | A resolved type outside the 22 in-scope types fails with `<type> type action is not suppor | action-server/src/main/java/com/kairon/action/actions/ActionFactory.java:20-31 — Message format is correct (test unsupportedTypeStays200), but prompt_action and database_action implementations are registered, so those deferred types run instead of failing. |
| R1 | `next_action` is stripped of surrounding whitespace but never lowercased: `My_Action` does | action-server/src/main/java/com/kairon/action/server/ActionProcessor.java:35 — next_action is never stripped (Maps.str only); case is preserved, but ' my_action ' will not match. |
| R3 | One failure mail is attempted (R6) | action-server/src/main/java/com/kairon/action/support/ActionSupport.java:97-103 — failureMail is a stub that only logs 'mail suppressed'; no SMTP send is attempted. |
| R3 | That document contains `intent`, `action`, `sender`, `exception` (the exception text), `bo | action-server/src/main/java/com/kairon/action/support/ActionSupport.java:85-94 — trigger_info is never written on the catch-all document (timestamp is added by MongoActionCatalog.insert). |
| R3 | `trigger_info` equals `{"trigger_name":"","trigger_type":"implicit","trigger_id":""}` when | action-server/src/main/java/com/kairon/action/support/ActionSupport.java:85-94 — trigger_info is absent, so the implicit default is not written. |
| R4 | Declared fields appear in the order `type, intent, action, sender, headers, url, request_m | action-server/src/main/java/com/kairon/action/support/ActionSupport.java:62-82 — Order written is type,intent,action,sender,exception,bot_response,bot,status,user_msg,request_id,trigger_info,extras, then timestamp appended last on insert; headers/url/request_method/etc. are not placed in declared order. |
| R4 | `request_id` equals the response `X-Kairon-Request-ID` value | action-server/src/main/java/com/kairon/action/support/ActionSupport.java:73 — request_id comes from the incoming header only; with no header it is null and no UUID is generated or echoed. |
| R4 | `trigger_info` equals the request `trigger_info` when present, else `{"trigger_name":"","t | action-server/src/main/java/com/kairon/action/runtime/ActionContext.java:24-30 — Defaults are right, but the log rebuilds only the 3 known keys instead of storing the request trigger_info as-is (ActionSupport.java:74-78). |
| R5 | For every in-scope type, a Success log contains `type` and every field listed for it in th | action-server/src/main/java/com/kairon/action/actions/HttpAction.java:103-108 — http_action lacks time_elapsed and events[]; kairon_bot_response lacks raw_gpt_response; pyscript/live_agent/callback/schedule lack messages. |
| R5 | For every in-scope type, the field set of each recorded fixture's log equals the Python re | action-server/src/main/java/com/kairon/action/support/ActionSupport.java:62-82 — save() always writes action, bot_response and user_msg for every type (e.g. web_search, pipedrive, store_page), and several listed fields are missing, so field sets cannot equal Python. |
| R5 | The http_action `api_call` sub-document contains masked `headers`, `method`, `url`, `paylo | action-server/src/main/java/com/kairon/action/actions/HttpAction.java:103-108 — No api_call sub-document exists. |
| R5 | The http_action `filled_slots` sub-document contains `data`, `slot_eval_log`, `time_elapse | action-server/src/main/java/com/kairon/action/actions/HttpAction.java:103-108 — No filled_slots sub-document exists. |
| R5 | http_action `events[]` contains sub-documents with `type` values `slots`, `response`, `api | action-server/src/main/java/com/kairon/action/actions/HttpAction.java:103-108 — No events[] sub-document list is written for http_action. |
| R6 | A catch-all failure (R3) causes one SMTP message to the configured support address | action-server/src/main/java/com/kairon/action/support/ActionSupport.java:97-103 — failureMail only logs; no SMTP message is sent. |
| R6 | A request that fails once produces exactly one mail, never two | action-server/src/main/java/com/kairon/action/support/ActionSupport.java:97-103 — Call sites are single per path, but zero mails are produced because there is no SMTP send. |
| R6 | An in-action failure that writes a Failed log and returns 200 with the action's fallback u | action-server/src/main/java/com/kairon/action/actions/HttpAction.java:98 — HttpAction calls failureMail on failure, but the helper sends no SMTP message. |
| R6 | Mail template and wording match the Python mail (needs human review) | action-server/src/main/java/com/kairon/action/support/ActionSupport.java:97-103 — There is no mail template at all, only a log line. |
| R6 | The mail body contains the action name, bot, exception text, stack trace, slot values and  | action-server/src/main/java/com/kairon/action/support/ActionSupport.java:97 — failureMail(bot, action, userText, error) takes no stack trace or slot values. |
| R6 | The webhook response is returned without waiting for the mail send to complete | action-server/src/main/java/com/kairon/action/server/ActionProcessor.java:69 — failureMail is called synchronously on the request thread; there is no async dispatch. |

## Changelog
- 2026-10-26: Initial draft from approved design.
- 2026-10-26: Review iteration 1 fixes (dependency cycles, compose secrets, scheduling endpoint contract, failure-mail paths, missing sender_id, dependency graph).
- 2026-10-26: Brownfield gap pass against existing port: 20 [GAP], 0 [UNVERIFIED] markers added.
- 2026-10-26: Build wave 1: R3 catch-all response criterion corrected to literal Python (handlers/action.py:25-31 keeps dispatcher messages); gap marker removed.
- 2026-10-26: Tier 0 gate (inspector): R3 gains the log-intent rule (no fallback skip; null without intent_ranking).
