---
created: "2026-10-26T12:44:00Z"
last_edited: "2026-10-26T14:00:00Z"
---

# Cavekit: Core Actions

## Scope
The seven action types with no external system integration: slot_set_action, form_validation_action, two_stage_fallback, kairon_bot_response (`utter_*`), kairon_voice_disconnect, store_page_action and callback_action. Each must produce the same webhook response, `action_server_logs` record and Mongo writes as the existing Python action server. Base log fields are defined in cavekit-dispatch-and-logging.md R4.

See context/refs/research-brief-java-action-server-port.md for evidence.

## Requirements

### R1: slot_set_action
**Description:** Sets or resets configured slots.
**Acceptance Criteria:**
- [ ] Config is read from collection `slot_set_action` by `bot`, `name`, `status: true`
- [ ] A `set_slots` entry with type `from_value` returns the slot with the configured `value`
- [ ] A `set_slots` entry with any other type returns the slot with `null`
- [ ] Returned slots contain only the configured slot names (no `kairon_action_response`)
- [ ] `responses` is `[]`
- [ ] The log has `type: "slot_set_action"`, `action` and `messages[]` with entries `Setting slot '<name>' to '<value>'.` or `Resetting slot '<name>' value to None.`
- [ ] The log `status` is always `Success`
- [ ] No failure utterance exists for this action
**Dependencies:** cavekit-dispatch-and-logging.md R4

### R2: form_validation_action
**Description:** Validates the tracker's `requested_slot` against configured rules.
**Acceptance Criteria:**
- [ ] Config is read from collection `form_validation_action` by `bot`, `name`, `status: true`, and the entry whose `slot` equals tracker `requested_slot` is used
- [ ] An empty `requested_slot` returns `{}`, no responses, and writes no log
- [ ] A non-empty `validation_semantic` is evaluated via the expression evaluator
- [ ] A valid value returns `{<requested_slot>: <value>}` where value is `slot_set.value` when `slot_set.type` is `custom` and that value is truthy, the value of the slot named by `slot_set.value` when `slot_set.type` is `slot`, and otherwise the slot's current tracker value
- [ ] A valid value utters `valid_response` as text when non-empty, and nothing when empty
- [ ] An invalid value returns `{<requested_slot>: null}`
- [ ] An invalid value utters `invalid_response` as text when non-empty (this is the failure utterance)
- [ ] The log has `type: "form_validation_action"`, `action` = tracker `followup_action`, `messages[]`
- [ ] The log `status` is `Success` only when validation passed; it is `Failed` on a validation miss and also when no validation entry matches the slot, in which case `messages[]` contains `Skipping validation as no validation config found for slot: <slot>` and the slot keeps its current value
**Dependencies:** cavekit-outbound-clients.md R6, cavekit-dispatch-and-logging.md R4

### R3: two_stage_fallback
**Description:** Offers recommendation buttons when the bot is unsure.
**Acceptance Criteria:**
- [ ] Config is read from collection `kairon_two_stage_fallback_action` by `bot`, `name`, `status: true`
- [ ] [GAP] With `use_intent_ranking` true, button texts come from training examples of the ranked intents; otherwise from a training-example text search on the user message, limited to `count`
- [ ] A trigger rule with `is_dynamic_msg` true adds a button `{text, payload}` with payload `/<payload>{"kairon_user_msg": "<latest user message>"}`
- [ ] A trigger rule with a non-empty `message` (and `is_dynamic_msg` false) adds payload `/<payload>{"kairon_user_msg": "<message>"}`
- [ ] A trigger rule with neither adds payload `/<payload>`
- [ ] With recommendations, one message is uttered with `text` = `fallback_message` and `buttons` = the recommendations
- [ ] With no recommendations, one message is uttered with `response: "utter_default"`
- [ ] Returned slots are `{}`
- [ ] [GAP] The log has `type: "two_stage_fallback"`, `bot_response` = Python repr of the recommendations list, `exception`
- [ ] [UNVERIFIED] No dedicated failure utterance exists; on exception responses and log match the recorded Python fixture (needs human review)
**Dependencies:** cavekit-templating-and-secrets.md R7, cavekit-dispatch-and-logging.md R4

### R4: kairon_bot_response (utter_*)
**Description:** Utters a domain response by name. LLM rephrase is out of scope.
**Acceptance Criteria:**
- [ ] No per-type config collection is read; `bot_settings` is read for the rephrase flag
- [ ] One message is uttered with `response` = the `utter_*` name
- [ ] Returned slots are `{"kairon_action_response": {"response": "<utter_name>"}}`
- [ ] [GAP] The log has `type: "kairon_bot_response"`, `enable_rephrasing` = the bot settings `rephrase_response` value, `is_rephrased`, and `raw_gpt_response` (null when no rephrase happened); with rephrase disabled these are `false`, `false`, `null`
- [ ] [GAP] The log `bot_response` equals `{'response': '<utter_name>'}` (Python repr)
- [ ] On exception the action writes its own `Failed` log with `exception`, sends the failure mail, and still utters the response
**Dependencies:** cavekit-templating-and-secrets.md R7, cavekit-dispatch-and-logging.md R1

### R5: kairon_voice_disconnect
**Description:** Tells the voice channel to hang up.
**Acceptance Criteria:**
- [ ] No config collection is read
- [ ] One message is uttered with `custom` = `{"disconnect": true}`
- [ ] Returned slots are `{}`
- [ ] The log has `type: "kairon_voice_disconnect"` and `bot_response` = `{'disconnect': True}`
- [ ] No failure utterance exists for this action
**Dependencies:** cavekit-templating-and-secrets.md R7

### R6: store_page_action
**Description:** Issues an encrypted identifier and a store-page token.
**Acceptance Criteria:**
- [ ] Config is read from collection `store_page_action` by `bot`, `name`, `status: true`
- [ ] Returned slots are exactly `user_identifier`, `temp_token`, `store_page_name`, `callback_identifier`
- [ ] `user_identifier` is a Fernet token that decrypts to the identifier slot value
- [ ] `temp_token` is an HS256 store-page token per cavekit-templating-and-secrets.md R6
- [ ] `responses` is `[]` (no utterance, also on failure)
- [ ] An empty identifier slot produces two log records and empty events (cavekit-dispatch-and-logging.md R7)
- [ ] Any other error returns empty slots and writes a Failed log
- [ ] [GAP] The log has `type: "store_page_action"`, `exception` and no `bot_response` field
**Dependencies:** cavekit-templating-and-secrets.md R5, cavekit-templating-and-secrets.md R6, cavekit-dispatch-and-logging.md R3

### R7: callback_action
**Description:** Registers a callback and exposes its URL or identifier.
**Acceptance Criteria:**
- [ ] Config is read from collection `callback_action_config` by `bot`, `name`, `status: true` (missing: `No Async Callback action found for given action and bot`); the callback configuration is read from collection `callback_config` by `bot` and case-insensitive `name` (missing: `Callback Configuration with name '<name>' does not exist!`)
- [ ] The long token is a Fernet token (cavekit-templating-and-secrets.md R5) of the JSON object `{"bot", "callback_name", "validation_secret", "expire_in"}` where `validation_secret` is the Fernet-decrypted stored secret and the JSON is serialized as Python `json.dumps` would (cavekit-templating-and-secrets.md R7)
- [ ] When the configuration's `shorten_token` is false, the URL token is the long token
- [ ] [GAP] When `shorten_token` is true, the long token is written back to the `callback_config` document's `token_value` field, and the URL token is the configuration's `token_hash` encrypted with AES-CTR using the configured key and IV, base64url-encoded with padding stripped
- [ ] The `standalone` flag comes from the callback configuration
- [ ] One `callback_data` document is inserted with `action_name`, `callback_name`, `bot`, `sender_id`, `channel`, `metadata`, `identifier`, `callback_url`, `timestamp`, `is_valid: true`
- [ ] `identifier` is a UUID version 7 rendered as 32 lowercase hex characters
- [ ] `callback_url` is the async callback base URL + `/s/{token}` for standalone callbacks, else + `/d/{identifier}/{token}`
- [ ] Returned slots are `{<dynamic_url_slot_name>: <identifier>}` when standalone, else `{<dynamic_url_slot_name>: <callback_url>}`; no `kairon_action_response`
- [ ] When `dispatch_bot_response` is true (default), `bot_response` is uttered as text with `{callback_url}` replaced by the URL
- [ ] When `dispatch_bot_response` is false, `responses` is `[]`
- [ ] [GAP] The log has `type: "callback_action"`, `callback_url`, `callback_url_slot`, `identifier`, `metadata[]`, `bot_response`, `messages`, `exception`
- [ ] [UNVERIFIED] No dedicated failure utterance exists; on exception responses and log match the recorded Python fixture (needs human review)
**Dependencies:** cavekit-templating-and-secrets.md R1, R5, R7; cavekit-config-and-deploy.md R1, R2, R3

## Out of Scope
- LLM rephrasing in kairon_bot_response
- Integration actions (cavekit-integration-actions.md) and orchestration actions (cavekit-orchestration-actions.md)
- prompt_action, database_action, Lambda transports, native image

## Cross-References
- See also: cavekit-orchestration-actions.md
- See also: cavekit-integration-actions.md
- See also: cavekit-webhook-contract.md
- See also: cavekit-dispatch-and-logging.md
- See also: cavekit-templating-and-secrets.md
- See also: cavekit-outbound-clients.md
- See also: cavekit-parity-harness.md
- See also: cavekit-config-and-deploy.md

## Source Traceability
- R1: kairon/actions/definitions/set_slot.py:30-58; kairon/shared/actions/data_objects.py:336
- R2: kairon/actions/definitions/form_validation.py:28-108; kairon/shared/actions/data_objects.py:374; kairon/shared/actions/utils.py:1086-1098
- R3: kairon/actions/definitions/two_stage_fallback.py; kairon/shared/actions/data_objects.py:827
- R4: kairon/actions/definitions/bot_response.py; kairon/shared/data/data_objects.py:903
- R5: kairon/actions/definitions/voice_disconnect.py
- R6: kairon/actions/definitions/store_page.py:69-71; kairon/shared/actions/data_objects.py:535; kairon/shared/auth.py:159
- R7: kairon/actions/definitions/callback_action.py; kairon/shared/actions/data_objects.py:1073; kairon/shared/callback/data_objects.py:50-96 (Fernet + AES-CTR helpers), 109, 190-209 (get_auth_token), 280-327

## Gap Summary
Brownfield verification against the existing port (2026-10-26): 50 met, 7 gaps, 2 unverified by code reading.
Criteria prefixed `[GAP]` are not satisfied by the current code; `[UNVERIFIED]` need runtime, fixture, or human confirmation.

| Req | Gap | Evidence |
|---|---|---|
| R3 | The log has `type: "two_stage_fallback"`, `bot_response` = Python repr of the recommendati | action-server/src/main/java/com/kairon/action/actions/TwoStageFallbackAction.java:112 — bot_response is Jsons.pythonDumps(recommendations), which is JSON with double quotes and null, not Python str() repr with single quotes and None. |
| R3 | With `use_intent_ranking` true, button texts come from training examples of the ranked int | action-server/src/main/java/com/kairon/action/actions/TwoStageFallbackAction.java:66-83 — The intent-ranking branch matches (intents[1:1+count]), but the search does an in-memory case-insensitive substring scan over training_examples instead of Mongo $text search ordered by text_score, so results and order can differ. |
| R4 | The log `bot_response` equals `{'response': '<utter_name>'}` (Python repr) | action-server/src/main/java/com/kairon/action/support/ActionSupport.java:69 — bot_response is String.valueOf(LinkedHashMap), which gives {response=utter_x}, not Python repr {'response': 'utter_x'}. |
| R4 | The log has `type: "kairon_bot_response"`, `enable_rephrasing` = the bot settings `rephras | action-server/src/main/java/com/kairon/action/actions/BotResponseAction.java:62 — enable_rephrasing logs the real settings flag (can be true), is_rephrased can be true, and raw_gpt_response is never written. |
| R6 | The log has `type: "store_page_action"`, `exception` and no `bot_response` field | action-server/src/main/java/com/kairon/action/support/ActionSupport.java:69 — save() always writes a bot_response key (null) on store_page logs. Python mongoengine omits None fields. |
| R7 | The log has `type: "callback_action"`, `callback_url`, `callback_url_slot`, `identifier`,  | action-server/src/main/java/com/kairon/action/actions/CallbackAction.java:109-114 — The log has callback_url, callback_url_slot, identifier, metadata, bot_response and exception, but no 'messages' field (Python logs the message from handle_utter_bot_response). |
| R7 | When `shorten_token` is true, the long token is written back to the `callback_config` docu | action-server/src/main/java/com/kairon/action/support/ActionSupport.java:626-627 — When shorten_token is set, the raw token_hash is returned: there is no AES-CTR encryption, no base64url encoding, and no token_value write-back to callback_config. |

## Changelog
- 2026-10-26: Initial draft from approved design.
- 2026-10-26: Review iteration 1 fixes (dependency cycles, compose secrets, scheduling endpoint contract, failure-mail paths, missing sender_id, dependency graph).
- 2026-10-26: Review iteration 2 fixes (scheduling rejection semantics, callback token derivation, AES IV, cross-references, tiering).
- 2026-10-26: Brownfield gap pass against existing port: 8 [GAP], 2 [UNVERIFIED] markers added.
