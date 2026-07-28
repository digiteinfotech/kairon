---
created: "2026-07-23T00:00:00Z"
last_edited: "2026-07-28T12:00:00Z"
complexity: medium
---

# Cavekit: Catalog URL Dispatch

## Scope
Dispatch-time behavior for catalog custom responses. When the WhatsApp channel's `send_custom_json` receives a custom payload marked as catalog type, it must retrieve the conversation tracker, resolve an identifier, build a catalog URL, and send that URL to the user as a labeled link when the payload supplies a non-empty label, or as a plain text message otherwise. This kit covers catalog configuration, catalog type registration in `type_list`, catalog detection at dispatch, tracker retrieval via `AgentProcessor`, identifier resolution (slot or literal), the missing-slot fallback, identifier encryption, session-token generation, URL assembly, text-or-link dispatch, and action logging. The stored payload convention is defined in cavekit-catalog-custom-response.md and is a prerequisite.

## Requirements

### R1: Catalog Configuration
**Description:** A base catalog URL must be configurable through system configuration and available to the runtime.
**Acceptance Criteria:**
- [ ] System configuration contains a catalog section with a url key.
- [ ] After configuration load, the configured base catalog URL is readable by the dispatch runtime.
- [ ] The url key supports the same environment-variable interpolation used by other system configuration values.
**Dependencies:** none.

### R2: Catalog Type Registration and Detection
**Description:** The catalog type must be registered in `type_list` so `send_custom_json` routes it to catalog handling, and all other types must be unaffected.
**Acceptance Criteria:**
- [ ] `"catalog"` is present in `type_list` in system metadata (system.yaml).
- [ ] When `send_custom_json` receives `messagetype == "catalog"`, the catalog dispatch path is taken.
- [ ] When `send_custom_json` receives any other type in `type_list`, existing dispatch behavior is unchanged.
- [ ] When `send_custom_json` receives a type absent from `type_list`, existing fallback behavior is unchanged.
**Dependencies:** R1; cavekit-catalog-custom-response.md R1.

### R3: Tracker Retrieval
**Description:** Before identifier resolution, the dispatch path must retrieve the live conversation tracker for the current sender.
**Acceptance Criteria:**
- [ ] The dispatch path calls `AgentProcessor.get_agent(bot_id).tracker_store.retrieve(sender_id)` using the `assistant_id` kwarg and the `recipient_id` argument of `send_custom_json`.
- [ ] If the tracker cannot be retrieved, no URL is assembled and no message is dispatched; the failure is logged.
**Dependencies:** R2.

### R4: Slot-Based Identifier Resolution
**Description:** When the payload's identifier type is slot, the identifier must be taken from the conversation slot named by the identifier value.
**Acceptance Criteria:**
- [ ] When the identifier type is `"slot"`, the runtime reads the slot whose name equals the identifier value from the retrieved tracker.
- [ ] When that slot is present and its value is a non-empty string, its value becomes the resolved identifier.
- [ ] When that slot is present but its value is an empty string, resolution is treated the same as absent/null (triggers R6 fallback).
**Dependencies:** R3.

### R5: Literal Identifier Resolution
**Description:** When the payload's identifier type is value, the identifier value itself must be used as the identifier.
**Acceptance Criteria:**
- [ ] When the identifier type is `"value"`, the resolved identifier equals the payload's identifier value verbatim.
- [ ] Literal resolution does not read any conversation slot.
**Dependencies:** R2.

### R6: Missing-Slot Fallback
**Description:** When slot-based resolution cannot produce an identifier, no message must be dispatched and the failure must be logged.
**Acceptance Criteria:**
- [ ] When the identifier type is `"slot"` and the named slot is absent, null, or an empty string, no URL is assembled and no message is dispatched to the user.
- [ ] The failure is recorded in the action log for that dispatch.
**Dependencies:** R4.

### R7: Identifier Encryption
**Description:** The resolved identifier must be encrypted before it is placed in the URL.
**Acceptance Criteria:**
- [ ] The identifier segment placed in the URL is the encrypted form of the resolved identifier, not its plaintext value.
- [ ] Encryption is applied to the resolved identifier produced by R4 or R5.
**Dependencies:** R4, R5.

### R8: Session Token Generation
**Description:** A session token scoped to the conversation sender and the bot must be generated per dispatch and included in the URL.
**Acceptance Criteria:**
- [ ] The generated token carries the conversation sender id under a `sub` claim.
- [ ] The generated token carries the bot id under a `bot` claim.
- [ ] The token is generated per dispatch, not stored on the response.
**Dependencies:** R2.

### R9: URL Assembly
**Description:** The catalog URL must be assembled in a fixed structure from the configured base, page name, bot id, encrypted identifier, and token.
**Acceptance Criteria:**
- [ ] The assembled URL has the structure `{catalog_url}/{page_name}/{bot_id}/{encrypted_identifier}?token={token}`.
- [ ] The page name segment is the payload's page name used literally, not resolved from a slot.
- [ ] The base URL is the configured value from R1, the encrypted identifier is from R7, and the token is from R8.
**Dependencies:** R1, R7, R8.

### R10: Text or Link Dispatch
**Description:** The assembled catalog URL must be delivered to the user either as a labeled hyperlink or as plain text, determined solely by whether the payload's label value is a non-empty, non-whitespace-only string.
**Acceptance Criteria:**
- [ ] When the payload's `label` value is a non-empty, non-whitespace-only string, the dispatched message is a custom payload of the existing link type, carrying the link data for that type.
- [ ] In that link dispatch, the link target is the assembled URL from R9 and the link's visible text is the payload's `label` value verbatim.
- [ ] The link data has the structure `[{"children": [{"type": "link", "href": "<assembled_url>", "children": [{"text": "<label>"}]}]}]`.
- [ ] The link dispatch uses the already-supported `link` type recognized by the existing custom-payload conversion path; no new payload type is introduced.
- [ ] When the payload's `label` is absent or null, the assembled URL is dispatched as plain text using the same text-message mechanism used for text responses.
- [ ] When the payload's `label` is an empty string or contains only whitespace, it is treated as absent and the assembled URL is dispatched as plain text by the same mechanism.
- [ ] For a given dispatch the URL is delivered exactly once — either as link or as text, never both.
**Dependencies:** R9; cavekit-catalog-custom-response.md R1.

### R11: Action Logging
**Description:** Every catalog dispatch attempt must be recorded in the action log consistent with existing bot-response logging.
**Acceptance Criteria:**
- [ ] A catalog dispatch produces an action log entry consistent with existing bot-response logging, recording the action name.
- [ ] A successful dispatch is logged with success status; a missing-slot fallback (R6) is logged with failure status.
**Dependencies:** R6, R10.

## Out of Scope
- Payload storage, retrieval, and round-trip (see cavekit-catalog-custom-response.md).
- Any new API endpoint or response type value.
- Token expiry configuration, refresh, or revocation.
- The catalog page frontend and rendering of the linked page.
- Resolving the page name from a slot (page name is always literal).
- NLG-layer interception — dispatch happens entirely within the WhatsApp channel handler.

## Cross-References
- See also: cavekit-catalog-custom-response.md (prerequisite — supplies the stored catalog payload).

## Source Traceability
- `system.yaml` — `catalog.url` configuration (R1); `type_list` entry for `"catalog"` (R2).
- `kairon/chat/handlers/channels/whatsapp.py` — `WhatsappBot.send_custom_json()`, the dispatch entry point (R2, R3, R4, R5, R6, R9, R10, R11).
- `kairon/chat/agent_processor.py` — `AgentProcessor.get_agent(bot_id).tracker_store.retrieve(sender_id)`, tracker retrieval (R3). Same pattern used in `voice.py:178-179`.
- `kairon/shared/utils.py` — `Utility.environment` (config access) and `Utility.encrypt_message` (identifier encryption) (R1, R7).
- `kairon/shared/auth.py` — `Authentication.create_access_token` (session token) (R8).
- `kairon/chat/converters/channels/responseconverter.py` — the existing `link` custom-payload conversion path reused for labeled dispatch (R10).

## Changelog
- 2026-07-23: Initial draft of the revised design. Replaces sender-id encryption + slot-resolved page name with identifierType-based resolution (slot/value), encrypted resolved identifier, literal page name, and a missing-slot drop-and-log fallback.
- 2026-07-28: Updated R9 to support optional label-based link dispatch. When label present, URL dispatched via existing link mechanism; when absent, plain text URL (backward compatible).
- 2026-07-28: Revised dispatch path. Entry point moved from NLG / ActionKaironBotResponse to `WhatsappBot.send_custom_json`. Added R2 (type_list registration) and R3 (tracker retrieval via AgentProcessor). Renumbered R3–R10 → R4–R11.
