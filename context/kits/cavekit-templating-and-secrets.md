---
created: "2026-10-26T12:44:00Z"
last_edited: "2026-10-26T14:00:00Z"
---

# Cavekit: Templating and Secrets

## Scope
Pure transformations from action config plus tracker to strings and values: URL/text placeholders, response templates, parameter resolution, evaluation context, Python repr and `json.dumps` reproduction, and the crypto these need (Fernet, HS256 JWT). No network calls. Which action uses which template is defined in the action kits.

See context/refs/research-brief-java-action-server-port.md for evidence.

## Requirements

### R1: URL and text placeholder grammar
**Description:** Placeholders are replaced in the exact Python order.
**Acceptance Criteria:**
- [ ] Replacement order is `$SENDER_ID`, then `$INTENT`, then `$USER_MESSAGE`, then `$$name`, then remaining `$name`
- [ ] `$INTENT` becomes an empty string when the latest message has no intent
- [ ] `$USER_MESSAGE` uses the `kairon_user_msg` entity value when the latest message text starts with `/`, else the message text
- [ ] `$$name` becomes the bot's key-vault value for `name`, or an empty string when the key is missing
- [ ] Each remaining match of `\$\w+` becomes the value of the slot with that name, or an empty string when the slot is null or absent
- [ ] Placeholders inside query strings (e.g. `?q=$city`) are replaced
- [ ] [UNVERIFIED] Output equals the Python output for every templating case in the recorded fixtures
**Dependencies:** none

### R2: Response template grammar
**Description:** Response templates resolve against an HTTP response body.
**Acceptance Criteria:**
- [ ] `${RESPONSE}` becomes the whole body serialized as R7 `json.dumps` would
- [ ] `${a.b.0}` resolves dict key `a`, then key `b`, then list index `0`
- [ ] [GAP] A resolved dict value is rendered as R7 `json.dumps`; any other value is rendered as Python `str()`
- [ ] A non-empty template against a body that is neither a dict nor a list fails with `Could not find value for keys in response`
- [ ] An empty template returns the raw body unchanged
**Dependencies:** R7

### R3: Parameter resolution
**Description:** Config parameters resolve by `parameter_type`, with decryption and log masking.
**Acceptance Criteria:**
- [ ] Type `value` returns the configured value
- [ ] Type `slot` returns the named slot's value
- [ ] [GAP] Types `sender_id`, `user_message`, `intent` and `latest_message` return the corresponding tracker values
- [ ] Type `chat_log` returns an object with keys `sender_id`, `session_started`, `conversation`
- [ ] Type `key_vault` returns the decrypted key-vault value, or `null` with no error when the key is missing
- [ ] A `value` parameter with `encrypt: true` is Fernet-decrypted before use (R5)
- [ ] The logged form of an encrypted parameter is masked, leaving the configured number of characters unmasked
**Dependencies:** R5, cavekit-config-and-deploy.md R1

### R4: Evaluation context
**Description:** The context sent to the expression and pyscript evaluators has the Python key set.
**Acceptance Criteria:**
- [ ] [GAP] The context contains `sender_id`, `user_message`, `slot`, `intent`, `chat_log`, `latest_message`, `kairon_user_msg`, `session_started` and `bot`
- [ ] [GAP] `key_vault` (all decrypted secrets for the bot) is present only when requested by the action config
- [ ] [UNVERIFIED] The context sent for each recorded fixture equals the recorded outbound evaluator body after normalization
**Dependencies:** R3

### R5: Fernet interoperability
**Description:** The port reads and writes Fernet tokens interchangeably with Python.
**Acceptance Criteria:**
- [ ] [UNVERIFIED] Every vector in the public Fernet specification decrypts to its expected plaintext
- [ ] [UNVERIFIED] A token produced by Python with the configured key decrypts in the port to the same plaintext
- [ ] [UNVERIFIED] A token produced by the port decrypts in Python to the same plaintext
- [ ] A token with a timestamp older than 60 seconds still decrypts (no TTL enforcement)
- [ ] A token with a tampered byte or wrong key fails with an error
**Dependencies:** cavekit-config-and-deploy.md R2

### R6: HS256 JWT minting
**Description:** Store-page and agent-integration tokens match the tokens the Python server mints.
**Acceptance Criteria:**
- [ ] Tokens use algorithm `HS256` and the configured secret
- [ ] The decoded header has keys in order `typ`, `alg`
- [ ] [UNVERIFIED] The store-page JWT payload has exactly `sub`, `version: "2.0"`, `exp`, `iat`; `sub` is a Fernet token (R5) of the Python `json.dumps` of the claims `{sub: <sender id>, bot, exp: <int>, iat: <int>, jti: <uuid7 string>, access-limit: ["/api/bot/.+/customer_data/.*", "/api/bot/.+/store_page/metadata", "/api/bot/.+/data/collection/.*", "/api/bot/.+/store_page/exec/flow"], type: "store_page"}`; `exp` is `iat` plus the bot's `store_page_token_expiry` minutes, or 15 when unset
- [ ] The agent integration JWT payload has exactly `sub` and `version: "2.0"` (no `exp`, no `iat`); `sub` is a Fernet token of the Python `json.dumps` of `{sub: <sender id>, bot, type: "integration"}`
- [ ] [UNVERIFIED] Tokens are not byte-comparable (random Fernet IV, `jti`, `iat`); parity is verified by decrypting the port's `sub` with the Python Fernet key and comparing the claim set to Python's ignoring `jti`, `iat` and `exp` values, and by the Python server accepting a port-minted token (needs human review)
**Dependencies:** cavekit-config-and-deploy.md R2

### R7: Python repr and json.dumps parity
**Description:** A serializer reproduces Python `str(dict)` and `json.dumps` defaults for log fields and templates that store them.
**Acceptance Criteria:**
- [ ] [GAP] repr output uses single quotes for strings, and double quotes when the string contains `'`
- [ ] [GAP] repr output renders booleans as `True`/`False` and null as `None`
- [ ] repr of `{"disconnect": true}` equals `{'disconnect': True}`
- [ ] json output uses `", "` and `": "` separators
- [ ] json output escapes non-ASCII characters as `\uXXXX`
- [ ] [GAP] json output formats floats as Python does (e.g. `1e+16`, `1.0`)
- [ ] [GAP] json and repr output preserve key insertion order
- [ ] [GAP] Output equals strings captured from Python for every repr field in the recorded fixtures (two_stage_fallback, kairon_voice_disconnect, kairon_bot_response `bot_response`)
**Dependencies:** none

### R8: Sender id decryption
**Description:** A sender id that is a valid Fernet token is decrypted before use; otherwise it is used as-is.
**Acceptance Criteria:**
- [ ] [GAP] A sender id that is a Fernet token of `user@x.com` under the configured key resolves to `user@x.com`
- [ ] A sender id that is not a valid Fernet token resolves to itself unchanged
**Dependencies:** R5

## Out of Scope
- Making HTTP calls (cavekit-outbound-clients.md)
- Which action uses which template (action kits)
- Repr/json fields of database_action (deferred)
- prompt_action, database_action, Lambda transports, LLM rephrase, native image

## Cross-References
- See also: cavekit-webhook-contract.md
- See also: cavekit-dispatch-and-logging.md
- See also: cavekit-outbound-clients.md
- See also: cavekit-core-actions.md
- See also: cavekit-integration-actions.md
- See also: cavekit-orchestration-actions.md
- See also: cavekit-config-and-deploy.md

## Source Traceability
- R1: kairon/shared/actions/utils.py:458-492 (prepare_url)
- R2: kairon/shared/actions/utils.py:608-675 (prepare_response)
- R3: kairon/shared/actions/utils.py:254-289 (get_parameter_value); kairon/shared/utils.py:2020 (get_masked_value)
- R4: kairon/shared/actions/utils.py:360-384 (build_context)
- R5: kairon/shared/utils.py:1391-1407; kairon/shared/data/data_objects.py:1015-1018
- R6: kairon/shared/auth.py:159 (create_store_page_token), :250 (create_access_token); kairon/actions/definitions/store_page.py; kairon/actions/definitions/agent_action.py:65-75
- R7: kairon/actions/definitions/two_stage_fallback.py; kairon/actions/definitions/bot_response.py; kairon/actions/definitions/voice_disconnect.py
- R8: kairon/shared/utils.py:1401 (decrypt_message); kairon/shared/actions/utils.py (sender id handling)

## Gap Summary
Brownfield verification against the existing port (2026-10-26): 25 met, 10 gaps, 7 unverified by code reading.
Criteria prefixed `[GAP]` are not satisfied by the current code; `[UNVERIFIED]` need runtime, fixture, or human confirmation.

| Req | Gap | Evidence |
|---|---|---|
| R2 | A resolved dict value is rendered as R7 `json.dumps`; any other value is rendered as Pytho | action-server/src/main/java/com/kairon/action/support/ActionSupport.java:401-415 — Dicts render via Jsons.write (Jackson compact ',' ':' separators), not json.dumps; floats use Java toString (1.0E16). |
| R3 | Types `sender_id`, `user_message`, `intent` and `latest_message` return the corresponding  | action-server/src/main/java/com/kairon/action/support/ActionSupport.java:127-151 — sender_id, user_message and intent are handled, but latest_message has no branch and falls through to the configured value. |
| R4 | The context contains `sender_id`, `user_message`, `slot`, `intent`, `chat_log`, `latest_me | action-server/src/main/java/com/kairon/action/support/ActionSupport.java:105-117 — context() has every key except 'bot'; only HttpAction adds bot afterwards (HttpAction.java:54), so pyscript/callback/etc. contexts lack it. |
| R4 | `key_vault` (all decrypted secrets for the bot) is present only when requested by the acti | action-server/src/main/java/com/kairon/action/support/ActionSupport.java:113 — key_vault is always present (empty map when not requested), and callers hard-code keyVault=true instead of reading the action config. |
| R7 | Output equals strings captured from Python for every repr field in the recorded fixtures ( | action-server/src/main/java/com/kairon/action/actions/BotResponseAction.java:62 — bot_response is stored via String.valueOf(Map) -> '{response=utter_x}' (ActionSupport.java:69), and two_stage uses json.dumps not repr (TwoStageFallbackAction.java:112); no fixture test. |
| R7 | json and repr output preserve key insertion order | action-server/src/main/java/com/kairon/action/support/Jsons.java:66-77 — json output preserves LinkedHashMap order, but there is no repr serializer to satisfy the repr half. |
| R7 | json output formats floats as Python does (e.g. `1e+16`, `1.0`) | action-server/src/main/java/com/kairon/action/support/Jsons.java:64-65 — Non-integer numbers use Java Number.toString (1.0E16, not 1e+16). |
| R7 | repr output renders booleans as `True`/`False` and null as `None` | action-server/src/main/java/com/kairon/action/support/ActionSupport.java:401-446 — True/False/None only appear in the placeholder/list helpers; dicts nested there are rendered as JSON (true/null). |
| R7 | repr output uses single quotes for strings, and double quotes when the string contains `'` | action-server/src/main/java/com/kairon/action/support/ActionSupport.java:436-437 — No general repr serializer exists; the list-item helper always single-quotes and backslash-escapes ' rather than switching to double quotes. |
| R8 | A sender id that is a Fernet token of `user@x.com` under the configured key resolves to `u | action-server/src/main/java/com/kairon/action/runtime/TrackerState.java:34 — sender_id is taken verbatim; nothing calls decrypt on it. |

## Changelog
- 2026-10-26: Initial draft from approved design.
- 2026-10-26: Brownfield gap pass against existing port: 10 [GAP], 7 [UNVERIFIED] markers added.
