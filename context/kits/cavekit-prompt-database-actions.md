---
created: "2026-10-30T00:00:00Z"
last_edited: "2026-10-30"
---

# Cavekit: Prompt and Database Actions

## Scope
prompt_action and database_action: config gates, prompt assembly (including crud and nested-action sources), execution against the real LLM and vector services through cavekit-llm-vector-clients.md, webhook output, failure handling and `action_server_logs` records. Each must match the Python action server's responses, logs and outbound calls.

This kit supersedes the earlier deferral and remote-adapter design; the other kits point here for these two actions. Approved design 2026-10-30: no adapter; a nested database action inside a prompt contributes nothing (Python quirk kept); prompt_action never dispatches recommendation buttons.

## Requirements

### R1: Gates and config load
**Description:** Both actions check the FAQ feature first, then load active config.
**Acceptance Criteria:**
- [ ] [GAP] The FAQ check runs before the config lookup: with `llm_settings.enable_faq` false the action fails with `Faq feature is disabled for the bot! Please contact support.` and no config read
- [ ] [GAP] A bot with no `bot_settings` document is treated as Python's default settings (FAQ disabled) and fails with the same message
- [ ] [GAP] Config is read by `bot`, `name`, `status: true`
- [ ] [GAP] A missing prompt config fails with `No action found for given bot and name`
- [ ] [GAP] A missing database config fails with `No Vector action found for given action and bot`
- [x] `_id` is absent from the logged config (verified: ActionGapParityTest#promptActionDispatchesResponse, #promptActionLoggedConfigIsToMongoView, #databaseActionLoggedConfigIsToMongoView; PromptDatabaseGateTest#databaseConfigViewDropsIdAndFillsResponseDefaults)
**Dependencies:** cavekit-dispatch-and-logging.md R4

### R2: Prompt assembly
**Description:** LLM parameters are built from enabled `llm_prompts` in config order.
**Acceptance Criteria:**
- [ ] [GAP] Disabled prompts are skipped; enabled prompts are processed in config order
- [ ] [GAP] Each system prompt sets the system prompt to `{data}\n`; the last one wins
- [ ] [GAP] Query prompts accumulate `{name}:\n{data}\n` plus the instructions block into the query prompt and enable it
- [ ] [GAP] A `history` source yields the last `num_bot_responses` (default 5) bot turns with their user turns as chat messages, stopping at session start
- [ ] [GAP] History messages use role `user` for user turns and `assistant` for bot turns, oldest first
- [ ] [GAP] A `bot_content` source adds a similarity source with its collection, name, instructions, `top_results` (default 10) and `similarity_threshold` (default 0.70)
- [ ] [GAP] A `slot` source appends `{name}:\n{slot value}\n`, with a null slot rendered `None`
- [ ] [GAP] Any other source appends `{name}:\n{data}\n`
- [ ] [GAP] Context sources with instructions also append `Instructions on how to use {name}:\n{instructions}\n\n`
- [ ] [GAP] `hyperparameters`, `instructions` and `should_process_media` (from config `process_media`) reach the completion request
- [ ] [GAP] `user_question` of type `from_slot` uses that slot's value; otherwise the latest user text, where a text starting with `/` is replaced by the `kairon_user_msg` entity value
**Dependencies:** cavekit-llm-vector-clients.md R2, cavekit-templating-and-secrets.md R7

### R3: crud prompt source
**Description:** A `crud` source injects matching collection records into the context.
**Acceptance Criteria:**
- [ ] [GAP] `crud_config` supplies `collections`, `query_source` (`slot` or `value`, default `value`) and `result_limit` (default 10)
- [ ] [GAP] With `query_source` `slot`, a dict slot value is used as-is, a string is parsed as JSON, and a falsy value means no filter
- [ ] [GAP] An unparseable slot value fails with `Invalid JSON format in slot value: {value}`
- [ ] [GAP] With `query_source` `value`, a string query is parsed as JSON
- [x] An unparseable `value`-mode query string has no dedicated message: the JSON parse error text becomes the log `exception` (status `Failed`) and the action takes the generic prompt failure path in R5 (`failure_message` or default fallback response, failure mail sent) (verified: ActionGapParityTest#promptActionCrudValueModeBadJsonTakesGenericFailurePath, CrudSourceTest#valueModeBadJsonTakesGenericPromptFailurePath)
- [ ] [GAP] Records are read per collection by lowercased name and bot, ANDing one `filterable_attrs` element match `{key, value}` per truthy pair, limited to `result_limit`
- [ ] [GAP] Only each record's `data` is used, decrypted when the record `is_secure`
- [ ] [GAP] Keys and values of different lengths fail with `Keys and values lists must be of the same length.`
- [ ] [GAP] Each collection appends `Collection data for {name}:\n{Python list repr}\n`
- [ ] [GAP] After all collections, `Instructions on how to use collection {name}:\n{instructions}\n\n` is appended once when instructions exist
**Dependencies:** cavekit-templating-and-secrets.md R5, R7

### R4: Nested action source
**Description:** An `action` source runs another action and injects its response.
**Acceptance Criteria:**
- [ ] [GAP] The nested action is resolved by name through action type resolution and run with the same tracker, dispatcher, domain and request context
- [ ] [GAP] A successful nested action appends `{name}:\n{response}\n` plus the instructions block when instructions exist
- [ ] [GAP] A failed nested action appends nothing, while its own utterances and log record remain
- [x] A nested action whose type has no success property in Python (every type except http, google_search, live_agent, agent, callback, schedule and parallel; including database_action) runs to completion and then fails the prompt action with `'<PythonClassName>' object has no attribute 'is_success'` (e.g. `'ActionDatabase' object has no attribute 'is_success'`); its own dispatches and log remain (verified: NestedActionSourceTest#nestedDatabaseActionRunsThenFailsWithAttributeError, #everyNonDefinerTypeMapsToItsPythonClassName)
**Dependencies:** cavekit-dispatch-and-logging.md R1

### R5: Prompt execution and output
**Description:** prompt_action predicts via the LLM clients and reports like Python.
**Acceptance Criteria:**
- [ ] [GAP] Cognition handling (cavekit-llm-vector-clients.md R7) runs for a non-default first similarity collection, then the model check (R6) on `hyperparameters.model`, before any LLM call
- [ ] [GAP] Prediction uses invocation `prompt_action`, the tracker `media_ids` slot and the first similarity source's collection
- [x] A prediction result with `is_failure` true sets status `Failed` and `exception` to the result's exception (verified: ActionGapParityTest#promptActionPredictionFailureSetsFailed)
- [x] Log `events` are `[llm_response, slots_to_fill]` in that order (verified: ActionGapParityTest#promptActionDispatchesResponse)
- [x] The `llm_response` event has `response`, `llm_response_log` and `time_elapsed`; `slots_to_fill` has `data`, `slot_eval_log` and `time_elapsed` (verified: ActionGapParityTest#promptActionEventsShapeAndTotalElapsed)
- [ ] [GAP] Slots are filled from context `{data: <content>, context: <tracker context>}`
- [ ] [GAP] Returned slots include `kairon_action_response` = content and `llm_call_id` = the call id
- [x] On error, `bot_response` is the FAQ-disabled text for that error, else `failure_message`, else the default NLU fallback response (verified: ActionGapParityTest#promptActionFaqDisabledUttersFaqTextWithoutMail, #promptActionMissingSecretFailsBeforeSchemaLookup, #promptActionEmptyFailureMessageUsesDefaultFallback, #promptActionMissingConfigUsesDefaultFallbackAndMails)
- [x] A failure mail is sent on error except the FAQ-disabled error (verified: ActionGapParityTest#promptActionFaqDisabledUttersFaqTextWithoutMail, #promptActionMissingConfigUsesDefaultFallbackAndMails, #promptActionCrudValueModeBadJsonTakesGenericFailurePath)
- [x] When `dispatch_response` is true (default), one text message with `bot_response` is uttered with no buttons (verified: ActionGapParityTest#promptActionDispatchesResponse, #promptActionLoggedConfigIsToMongoView (dispatch_response absent), #promptActionDispatchResponseFalseUttersNothing)
- [x] The log carries `type, intent, action, sender, events, bot, exception, recommendations (null), bot_response, status, llm_response, kairon_faq_action_config, llm_logs, user_msg, media_ids, time_elapsed, trigger_info, llm_call_id, request_id` with `time_elapsed` = prediction plus slot-fill seconds (field order per R7) (verified: ActionGapParityTest#promptActionEventsShapeAndTotalElapsed)
**Dependencies:** R1, R2, cavekit-llm-vector-clients.md R6, R7, R8, cavekit-dispatch-and-logging.md R4, R6, cavekit-outbound-clients.md R5

### R6: Database execution and output
**Description:** database_action builds a payload, queries the vector store and composes a response.
**Acceptance Criteria:**
- [x] An unsupported `db_type` fails before payload building, leaving `messages` empty (verified: ActionGapParityTest#databaseActionRejectsUnknownDbTypeBeforeBuildingPayload)
- [x] A missing cognition schema fails before the payload is logged (verified: ActionGapParityTest#databaseActionMissingSchemaFailsBeforePayloadIsLogged)
- [ ] [GAP] A payload item of type `from_slot` uses the slot value, `from_user_message` the latest text (`/`-prefixed text replaced by the `kairon_user_msg` entity), otherwise `value`
- [ ] [GAP] A `payload_search` string is parsed as JSON; failure gives `Error converting payload to JSON: {value}`
- [ ] [GAP] Other query types concatenate their values with a single space under `embedding_search`
- [ ] [GAP] With `training_needed` false, the query uses the openrouter provider and secret (cavekit-llm-vector-clients.md R7)
- [ ] [GAP] The vector query is sent per cavekit-llm-vector-clients.md R5 and its result composed with context `{data, context}`
- [x] `messages` holds the payload, then the compose log, then the slot-eval log entries (verified: ActionGapParityTest#databaseActionDispatchesResponse)
- [x] On error, `bot_response` is `failure_response` (default `I have failed to process your request.` when config was not loaded) and a failure mail is sent, including for the FAQ-disabled error (verified: ActionGapParityTest#databaseActionFaqDisabledSendsFailureMail, #databaseActionMissingResponseConfigUsesDefaults, #databaseActionFailureLogOmitsFalsyBotResponseKeepsDynamicNulls)
- [x] When `response.dispatch` is true, `bot_response` is uttered as text, on both success and failure (verified: ActionGapParityTest#databaseActionSuccessLogKeyOrder, #databaseActionResponseWithoutDispatchDispatchesByDefault, #databaseActionDispatchFalseUttersNothing)
- [ ] [GAP] Returned slots are the filled slots plus `kairon_action_response`
**Dependencies:** R1, cavekit-llm-vector-clients.md R5, R7, cavekit-templating-and-secrets.md R2, cavekit-dispatch-and-logging.md R6, cavekit-outbound-clients.md R5

### R7: Logging parity, registration and config
**Description:** Log records, factory registration and configuration match Python.
**Acceptance Criteria:**
- [x] The database log `payload` is the Python repr of the payload (verified: ActionGapParityTest#databaseActionDispatchesResponse)
- [x] The database log `response` and `bot_response` are the Python repr of their values when truthy; when falsy, `response` is stored as null and `bot_response` (a declared field) is omitted (verified: ActionGapParityTest#databaseActionDispatchesResponse, #databaseActionSuccessLogKeyOrder, #databaseActionFailureLogOmitsFalsyBotResponseKeepsDynamicNulls)
- [x] Database log field order follows cavekit-dispatch-and-logging.md R4 (authoritative): non-null declared fields `type, intent, action, sender, headers, bot_response, exception, messages, bot, timestamp, status, trigger_info, request_id`, then dynamic fields `config, payload, response, user_msg` (verified: ActionGapParityTest#databaseActionSuccessLogKeyOrder, #databaseActionFailureLogOmitsFalsyBotResponseKeepsDynamicNulls, #databaseActionFaqDisabledSendsFailureMail)
- [x] Database log dynamic fields `payload` and `response` are present with null when falsy (declared null fields such as `exception` are omitted) (verified: ActionGapParityTest#databaseActionFailureLogOmitsFalsyBotResponseKeepsDynamicNulls, #databaseActionSuccessLogKeyOrder)
- [x] Prompt log field order follows cavekit-dispatch-and-logging.md R4: non-null declared fields, then dynamic fields `events, recommendations, llm_response, kairon_faq_action_config, llm_logs, user_msg, media_ids, time_elapsed, llm_call_id` (verified: ActionGapParityTest#promptActionEventsShapeAndTotalElapsed, #promptActionDispatchesResponse)
- [x] The logged prompt and database configs are the `to_mongo()` view: no `_id`, mongoengine defaults applied (a missing or null field takes its default, including embedded documents; null `hyperparameters` loads the LLMMetadata `openai` property defaults and fails with `Could not find any hyperparameters for openai LLM.` when none exist; null `db_type` runs as `qdrant`), declared field order (verified: ActionGapParityTest#promptActionLoggedConfigIsToMongoView, #promptActionNullHyperparametersWithoutMetadataFailsAtConfigLoad, #databaseActionLoggedConfigIsToMongoView; PromptDatabaseGateTest#promptConfigViewFillsEmbeddedDefaults, #databaseConfigViewDropsIdAndFillsResponseDefaults)
- [x] `prompt_action` and `database_action` resolve to their implementations through action type resolution (verified: ActionGapParityTest#promptActionDispatchesResponse, ActionGapParityTest#databaseActionDispatchesResponse)
- [x] Service configuration docs no longer describe prompt_action or database_action as deferred (verified: ConfigMappingTest#llmAndVectorRowsMatchApplicationYml asserts CONFIG.md has no "deferred" wording; T-126 removed the adapter keys `kairon.action.llm-url`/`vector-url`, ActionSettings llmUrl/vectorUrl and their javadocs; grep of action-server/src/main and CONFIG.md finds no adapter/deferred text)
- [ ] [GAP] The LLM and vector config keys listed in cavekit-config-and-deploy.md R1 are configurable as specified there
**Dependencies:** cavekit-templating-and-secrets.md R7, cavekit-dispatch-and-logging.md R1, R4, cavekit-config-and-deploy.md R1

## Known risks (accepted, parity with Python)

- crud slot mode passes a user-controlled slot value straight into the collection filter, so Mongo operators in the value (e.g. `$regex`, `$ne`) are interpreted as in Python. Scope stays bot + collection, but a user can pull any record of the named collection into the prompt, with `is_secure` fields decrypted, and decrypted data is persisted in `llm_logs`. Decision 2026-10-30: match Python; revisit if this action is exposed to untrusted end users.

## Out of Scope
- Model training and collection creation, including use of the embedding size
- Sparse and rerank embeddings
- LLMLogs persistence (written by the LLM server)
- Recommendation buttons on prompt_action
- A remote LLM/vector adapter

## Cross-References
- See also: cavekit-llm-vector-clients.md
- See also: cavekit-dispatch-and-logging.md
- See also: cavekit-templating-and-secrets.md
- See also: cavekit-core-actions.md
- See also: cavekit-integration-actions.md
- See also: cavekit-outbound-clients.md
- See also: cavekit-config-and-deploy.md (LLM/vector config keys in R1)

## Source Traceability
- R1: kairon/actions/definitions/prompt.py:37-44; kairon/actions/definitions/database.py:43-55
- R2: kairon/actions/definitions/prompt.py:176-287; kairon/shared/actions/utils.py:339-357 (prepare_bot_responses); kairon/shared/actions/data_objects.py:944 (num_bot_responses default 5)
- R3: kairon/actions/definitions/prompt.py:203-241 (no try/except around value-mode json.loads), 122-131 (generic failure path); kairon/shared/cognition/collection_processor.py:274-320
- R4: kairon/actions/definitions/prompt.py:242-249
- R5: kairon/actions/definitions/prompt.py:46-170
- R6: kairon/actions/definitions/database.py:57-140; kairon/shared/actions/utils.py:727-786 (get_payload)
- R7: kairon/actions/definitions/database.py:121-137 (ActionServerLogs kwargs); kairon/shared/actions/utils.py:327-336 and database.py:46-48 (to_mongo().to_dict(), _id popped); kairon/shared/actions/data_objects.py:235-246, 942-958 (field order and defaults), kairon/shared/utils.py:2180-2197 (default hyperparameters); kairon/actions/definitions/prompt.py:139-158; kairon/shared/actions/data_objects.py:263-282 (ActionServerLogs declared fields; DynamicDocument serializes non-null declared fields in declaration order, then dynamic fields in kwarg order with nulls kept, confirmed with mongoengine 0.29 `to_mongo()`); kairon/actions/definitions/factory.py

## Changelog
- 2026-10-30: Initial draft from approved design (real services, nested database quirk, no prompt buttons).
- 2026-10-30: Review fixes: log field order aligned to cavekit-dispatch-and-logging.md R4 (authoritative) per mongoengine serialization; config criterion references cavekit-config-and-deploy.md R1; history default 5 and role labels; value-mode JSON parse failure; crud instructions appended once; falsy `bot_response` omitted (declared field) rather than null; dependency on cavekit-outbound-clients.md R5 (script-mode compose and slot evaluation).
- 2026-10-30: R4 c4 corrected (nested action without a Python success property fails the prompt with AttributeError text); Known risks section added (crud operator injection accepted).
- 2026-10-30: T-125: R7 criterion added (logged configs are the to_mongo() view); R3 c5, R5 c3/c5/c8-c11, R6 c9/c10, R7 c2-c5 verified.
