---
created: "2026-10-26T12:44:00Z"
last_edited: "2026-10-26T14:00:00Z"
---

# Cavekit: Integration Actions

## Scope
The thirteen action types that each call one external system: http_action, email_action, google_search_action, web_search_action, jira_action, zendesk_action, pipedrive_leads_action, hubspot_forms_action, razorpay_action, live_agent_action, agent_action, voice_call_action and pyscript_action. Each must match the existing Python action server on webhook response, `action_server_logs` record and outbound side effects. Config is always matched by `bot`, action name and `status: true`. KAR = slot `kairon_action_response`. Base log fields: cavekit-dispatch-and-logging.md R4.

See context/refs/research-brief-java-action-server-port.md for evidence.

## Requirements

### R1: http_action
**Description:** Calls a configured HTTP endpoint and maps its response to an utterance and slots.
**Acceptance Criteria:**
- [ ] Config is read from `http_action_config`; key-vault values from `key_vault`
- [ ] When `dynamic_params` is set the body comes from the pyscript evaluator, else from `params_list` resolution
- [ ] URL and headers are templated per cavekit-templating-and-secrets.md R1 and R3
- [ ] The request uses the swallowing exchange (cavekit-outbound-clients.md R1), multipart when `media_ids` are present
- [ ] Response composition: `evaluation_type` `script` sends the template to the pyscript evaluator; `expression` (the default) validates the HTTP status (non-2xx fails) and then fills the template locally per cavekit-templating-and-secrets.md R2; an empty template yields a null result
- [ ] [GAP] Each `set_slots` entry is evaluated independently; one failing entry sets that slot to `null`, is logged, and does not fail the action
- [ ] Slots are emitted in order: dynamic_params slots, `kairon_action_response`, `http_status_code`, then `set_slots` (overriding earlier keys)
- [ ] An utterance is sent only when `response.dispatch` is true and the composed response is truthy
- [ ] [GAP] `dispatch_type` json parses a string response and sends it as `custom`; on decode error it sends text and logs `Failed to convert http response to json: ...`
- [ ] A list response sends one message per element: dict elements as `custom`, others as `text`
- [ ] Failure utterance: `I have failed to process your request`
- [ ] [GAP] Log: `type: "http_action"`, `action`, `url`, `request_method`, `bot_response`, `fail_reason` (on non-2xx), `exception`, `http_status_code`, `time_elapsed` (sum of the four timings), `events[]` per cavekit-dispatch-and-logging.md R5
- [ ] [GAP] The `filled_slots` sub-document `time_elapsed` equals the last slot's evaluation time only
**Dependencies:** cavekit-outbound-clients.md R1, R5, R6, R8; cavekit-templating-and-secrets.md R1-R4; cavekit-dispatch-and-logging.md R5

### R2: email_action
**Description:** Sends mail to configured recipients.
**Acceptance Criteria:**
- [ ] Config is read from `email_action_config`
- [ ] [GAP] `from_email` and `to_email` resolve as value or slot; SMTP credentials via parameter resolution
- [ ] [GAP] One SMTP message per recipient with subject `{sender_id} {subject}` and body = chat-log HTML or `custom_text`
- [ ] Slots: `{"kairon_action_response": <bot_response>}`
- [ ] When `dispatch_bot_response` is true (default) `response` is uttered as text; when false `responses` is `[]`
- [ ] Failure utterance: `I have failed to process your request`
- [ ] Log: `type: "email_action"`, `action`, `bot_response`, `exception`
**Dependencies:** cavekit-outbound-clients.md R7, cavekit-templating-and-secrets.md R3

### R3: google_search_action
**Description:** Searches Google Custom Search and utters results.
**Acceptance Criteria:**
- [ ] Config is read from `google_search_action`; `api_key` and `search_term` via parameter resolution
- [ ] The search term is the latest message text, or the `kairon_user_msg` entity when the text starts with `/`
- [ ] With an API key, the outbound request carries exactly `key`, `cx` (= `search_engine_id`), `q` and `num` (= `num_results`); `website` is not sent. Without an API key, the search term becomes `<term> site: <website>` when `website` is set
- [ ] When `dispatch_response` is true (default), an utterance is sent: formatted results on success, else the configured `failure_response` (the failure utterance); when false nothing is uttered
- [ ] Slots: `kairon_action_response`, plus `set_slot` = results when configured
- [ ] Log: `type: "google_search_action"`, `action`, `google_response`, `bot_response`, `exception`
**Dependencies:** cavekit-outbound-clients.md R1

### R4: web_search_action
**Description:** Searches via the configured web-search service URL.
**Acceptance Criteria:**
- [ ] Config is read from `web_search_action`; the request goes to the configured web-search URL with `topn` and `website`
- [ ] The search term follows the R3 rule
- [ ] When `dispatch_response` is true (default), an utterance is sent: formatted results on success, else the configured `failure_response` (the failure utterance); when false nothing is uttered
- [ ] Slots: `kairon_action_response`, plus `set_slot` = results when configured
- [ ] Log: `type: "web_search_action"`, `public_search_action_response`, `bot_response`, `exception`
**Dependencies:** cavekit-outbound-clients.md R1, cavekit-config-and-deploy.md R1

### R5: jira_action
**Description:** Creates a Jira issue.
**Acceptance Criteria:**
- [ ] Config is read from `jira_action`; `api_token` via parameter resolution
- [ ] The issue is created in `project_key` with `issue_type`, `parent_key` when set, summary `{sender_id} {summary}` and description = conversation message trail
- [ ] `response` is always uttered as text on success; slots `{"kairon_action_response": ...}`
- [ ] Failure utterance: `I have failed to create issue for you`
- [ ] Log: `type: "jira_action"`, `action`, `bot_response`, `exception`
**Dependencies:** cavekit-outbound-clients.md R1

### R6: zendesk_action
**Description:** Creates a Zendesk ticket.
**Acceptance Criteria:**
- [ ] Config is read from `zendesk_action`; the ticket goes to `subdomain` with `subject`, `tags` and comment = chat-log HTML
- [ ] `response` is always uttered as text on success; slots `{"kairon_action_response": ...}`
- [ ] Failure utterance: `I have failed to create issue for you`
- [ ] Log: `type: "zendesk_action"`, `action`, `bot_response`, `exception`
**Dependencies:** cavekit-outbound-clients.md R1

### R7: pipedrive_leads_action
**Description:** Creates a Pipedrive organization, person, lead and note.
**Acceptance Criteria:**
- [ ] Config is read from `pipedrive_leads_action`
- [ ] Organization, person, lead (`title`) and note requests are sent to `domain` in the recorded order
- [ ] `response` is always uttered as text on success; slots `{"kairon_action_response": ...}`
- [ ] Failure utterance: `I have failed to create lead for you`
- [ ] Log: `type: "pipedrive_leads_action"`, `bot_response`, `exception`
**Dependencies:** cavekit-outbound-clients.md R1

### R8: hubspot_forms_action
**Description:** Submits a HubSpot form.
**Acceptance Criteria:**
- [ ] Config is read from `hubspot_forms_action`
- [ ] A POST goes to `https://api.hsforms.com/submissions/v3/integration/submit/{portal_id}/{form_guid}` with the resolved `fields`, via the raising exchange
- [ ] `response` is always uttered as text on success; slots `{"kairon_action_response": ...}`
- [ ] Failure utterance: `I have failed to process your request`
- [ ] Log: `type: "hubspot_forms_action"`, `request_params` (= body), `api_response`, `bot_response`, `exception`
**Dependencies:** cavekit-outbound-clients.md R2

### R9: razorpay_action
**Description:** Creates a Razorpay payment link.
**Acceptance Criteria:**
- [ ] Config is read from `razorpay_action`
- [ ] A POST goes to `https://api.razorpay.com/v1/payment_links/` with basic auth `api_key`:`api_secret`, via the raising exchange
- [ ] The body is `{amount:<int>, currency, customer{username, email, contact}, notes{..., bot}}`
- [ ] An empty or non-numeric amount fails with `amount must be a whole number! Got X.` (X = the amount); a numeric amount is converted to an integer by truncation
- [ ] The response `short_url` is uttered as text; slots `{"kairon_action_response": <short_url>}`
- [ ] Failure utterance: `I have failed to process your request`
- [ ] Log: `type: "razorpay_action"`, `request` (= body), `api_response`, `bot_response`, `exception`
**Dependencies:** cavekit-outbound-clients.md R2

### R10: live_agent_action
**Description:** Hands the conversation to a live agent.
**Acceptance Criteria:**
- [ ] Config is read from `live_agent_action_config`
- [ ] When the live-agent service is unavailable, no handoff POST is made and the action does not raise
- [ ] Otherwise a POST of `{bot_id, sender_id, channel, request_id}` goes to `{live agent URL}/conversation/request` with `Authorization: Bearer <token>`; non-200 raises
- [ ] With no channel in the request (web), the message is `custom` = `{"action":"live_agent","response":<bot_response>}`; other channels get `text` = `bot_response`
- [ ] With `dispatch_bot_response` false, the web message is still sent with `"response":null`
- [ ] Returned slots are `{}`
- [ ] [UNVERIFIED] No dedicated failure utterance; on exception responses and log match the recorded Python fixture (needs human review)
- [ ] [GAP] Log: `type: "live_agent_action"`, `bot_response`, `messages[]`, `exception`
**Dependencies:** cavekit-config-and-deploy.md R1

### R11: agent_action
**Description:** Runs a simple agent.
**Acceptance Criteria:**
- [ ] Config is read from `agent_action_config`
- [ ] A POST goes to `{simple-agent URL}/agents/{bot}/{agent_id}/run/{sender}/simple` with body `{"message": ..., "session_id": null, "metadata": {}, "max_iterations": 1}`
- [ ] Headers carry `X-user` and `Authorization: Bearer <integration JWT>` (cavekit-templating-and-secrets.md R6); non-2xx raises
- [ ] The bot response is `api_response["output"]` (or empty) when the response is a JSON object, else Python `str(api_response)`; it is uttered as text only when `dispatch_bot_response` is true (default) and the response is non-empty
- [ ] Slots `{"kairon_action_response": ...}`
- [ ] Failure utterance: `I have failed to process your request.`
- [ ] Log: `type: "agent_action"`, `url`, `bot_response`, `api_response`, `exception`
**Dependencies:** cavekit-templating-and-secrets.md R6, cavekit-outbound-clients.md R1

### R12: voice_call_action
**Description:** Places an outbound voice call.
**Acceptance Criteria:**
- [ ] Config is read from `voice_call_action`; channel settings from the bot's voice channel config
- [ ] [GAP] `to_phone_number` resolves as slot or value; the provider's initiate-call request carries the call URL and status URL
- [ ] One `channel_logs` document is written with `type: "voice"`, `status: "initiated"`, `data{to, call_sid}`, `message_id` = call_sid or `unknown`, `bot`, `user`, `initiator: "bot"`
- [ ] When dispatching, `response` is uttered (default `I'm placing a call to you now.`); slots `{"kairon_action_response": ...}`
- [ ] Failure utterance: `I have failed to place the call`
- [ ] Log: `type: "voice_call_action"`, `bot_response`, `exception`
- [ ] [UNVERIFIED] Twilio is covered; coverage of other providers is confirmed (needs human review)
**Dependencies:** cavekit-config-and-deploy.md R3

### R13: pyscript_action
**Description:** Runs user Python via the pyscript evaluator.
**Acceptance Criteria:**
- [ ] Config is read from `pyscript_action_config`
- [ ] The evaluator call follows cavekit-outbound-clients.md R5 with the evaluation context
- [ ] Slots are the evaluator slots minus `bot`, plus `kairon_action_response`
- [ ] When `dispatch_response` is true, `bot_response` is uttered as `custom` when `response.type` is `json`, else as `text`
- [ ] Failure utterance: `I have failed to process your request`
- [ ] [GAP] Log: `type: "pyscript_action"`, `config` (full config), `bot_response`, `messages[]`, `exception`
**Dependencies:** cavekit-outbound-clients.md R5, cavekit-templating-and-secrets.md R4

## Out of Scope
- prompt_action and database_action (deferred)
- Lambda transports for pyscript and web search
- LLM rephrase, native image
- Telephony providers beyond those the Python server supports

## Cross-References
- See also: cavekit-config-and-deploy.md
- See also: cavekit-core-actions.md
- See also: cavekit-webhook-contract.md
- See also: cavekit-dispatch-and-logging.md
- See also: cavekit-templating-and-secrets.md
- See also: cavekit-outbound-clients.md
- See also: cavekit-parity-harness.md

## Source Traceability
- R1: kairon/actions/definitions/http.py:36-185; kairon/shared/actions/utils.py:678-716, 788-824
- R2: kairon/actions/definitions/email.py:62-79
- R3: kairon/actions/definitions/google.py:114; kairon/shared/actions/utils.py:545
- R4: kairon/actions/definitions/web_search.py; kairon/shared/actions/utils.py:570
- R5: kairon/actions/definitions/jira.py:101; kairon/shared/actions/utils.py:950
- R6: kairon/actions/definitions/zendesk.py; kairon/shared/actions/utils.py:983
- R7: kairon/actions/definitions/pipedrive.py; kairon/shared/actions/utils.py:1019-1073
- R8: kairon/actions/definitions/hubspot.py:65-70; kairon/shared/actions/utils.py:98-143
- R9: kairon/actions/definitions/razorpay.py:91
- R10: kairon/actions/definitions/live_agent.py:108-115; kairon/shared/live_agent/live_agent.py:20-61
- R11: kairon/actions/definitions/agent_action.py:65-75
- R12: kairon/actions/definitions/voice_call.py:79-87; kairon/shared/chat/data_objects.py:43
- R13: kairon/actions/definitions/pyscript.py; kairon/shared/actions/utils.py:759-785

## Gap Summary
Brownfield verification against the existing port (2026-10-26): 74 met, 9 gaps, 2 unverified by code reading.
Criteria prefixed `[GAP]` are not satisfied by the current code; `[UNVERIFIED]` need runtime, fixture, or human confirmation.

| Req | Gap | Evidence |
|---|---|---|
| R1 | Each `set_slots` entry is evaluated independently; one failing entry sets that slot to `nu | support/ActionSupport.java:364-375 — Each slot evaluated independently and set to null on failure, but the failure is swallowed with no slot_eval_log/log entry. |
| R1 | Log: `type: "http_action"`, `action`, `url`, `request_method`, `bot_response`, `fail_reaso | actions/HttpAction.java:103-108 — Log carries url, request_method, http_status_code, fail_reason, but no time_elapsed and no events[] (slots/response/api_call/params/filled_slots sub-documents). |
| R1 | The `filled_slots` sub-document `time_elapsed` equals the last slot's evaluation time only | actions/HttpAction.java:103-108 — No filled_slots sub-document or per-slot timing is recorded at all. |
| R1 | `dispatch_type` json parses a string response and sends it as `custom`; on decode error it | support/ActionSupport.java:483-501 — json dispatch parses and sends custom, falls back to text on decode error, but never logs 'Failed to convert http response to json: ...'. |
| R2 | One SMTP message per recipient with subject `{sender_id} {subject}` and body = chat-log HT | actions/EmailAction.java:47-51 — Subject and body are built per recipient but no SMTP message is sent; it only logs 'smtp is not configured; email not sent'. |
| R2 | `from_email` and `to_email` resolve as value or slot; SMTP credentials via parameter resol | actions/EmailAction.java:43-44,103-109 — from/to resolve as value or slot, but SMTP credentials (smtp_url, smtp_userid, smtp_password, port, tls) are never resolved. |
| R10 | Log: `type: "live_agent_action"`, `bot_response`, `messages[]`, `exception` | actions/LiveAgentAction.java:89 — save passes no extra fields; messages[] is not logged. |
| R12 | `to_phone_number` resolves as slot or value; the provider's initiate-call request carries  | actions/VoiceCallAction.java:58,72-78 — to_phone_number resolves slot/value, but the request goes to a generic settings voiceCallUrl, not the provider's (Twilio) initiate-call API; call_url/status_url are only body fields. |
| R13 | Log: `type: "pyscript_action"`, `config` (full config), `bot_response`, `messages[]`, `exc | actions/PyscriptAction.java:64-66 — Log includes config but no messages[] field. |

## Changelog
- 2026-10-26: Initial draft from approved design.
- 2026-10-26: Brownfield gap pass against existing port: 10 [GAP], 2 [UNVERIFIED] markers added.
- 2026-10-26: Build wave 1: R3 website criterion corrected to Python behaviour (website only used on the keyless path); gap marker removed.
