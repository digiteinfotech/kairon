---
created: "2026-10-30"
last_edited: "2026-10-30"
---
# Implementation Tracking: llm-vector-clients + prompt-database-actions

Build site: context/plans/build-site-llm-prompt-db.md

| Task | Status | Notes |
|------|--------|-------|
| T-100 | DONE | config keys llm.url/request_timeout, vector.db/key; legacy llmUrl/vectorUrl kept until T-126. T-107 must move/remove legacy yml lines before editing CONFIG.md rows (placeholderDefault matches first). |
| T-101 | DONE | catalog lookups (llm secret, model, cognition schema/data). Live-Mongo contract run gated on KAIRON_TEST_MONGO_URI, not yet run (12 skipped). |
| T-102 | DONE | jtokkit 1.1.0 pinned; checkAdvisories does not scan jtokkit (vetted via OSV lookup only). |
| T-103 | DONE | dynamic nulls kept; triggers T-112 (http fail_reason, bot_response raw_gpt_response updated). |
| T-104 | DONE | FaqGate: missing bot_settings/llm_settings/enable_faq = FAQ disabled (Python defaults). |
| T-105 | DONE | PromptParams extracted; num_bot_responses default 5; ContextSource hook for crud/action (T-113/T-114). |
| T-106 | DONE | DbPayload extracted; scalar payload_search accepted, Python str() concat and TypeError text. |
| T-107 | DONE | CONFIG.md rows; legacy llm-url/vector-url yml lines moved below new keys (T-126 deletes them + getters). |
| T-108 | DONE | LlmHttp (headers, llm timeout, 1 attempt, status phrases). Kit conflict: LLM R3 c4 says 404 -> 'Not Found' but Python's RetryClient(raise_for_status) path may yield 'Internal Server Error' for any non-2xx (outbound-clients R1 GAP). Reconcile kits before T-116. |
| T-109 | DONE | LlmSecrets; cross-language Fernet test passes. API: secret, checkModel, embeddingSecret, usesDefaultEmbeddingSecret. |
| T-110 | DONE | QdrantClient.search (5s, api-key only when set, urljoin drops base path). Rendering/concurrency left to T-119. Non-2xx/non-JSON texts approximated. |
| T-111 | DONE | prompt never dispatches buttons. |
| T-112 | DONE | form_validation no user_msg; callback metadata []; schedule data {}; prompt extras order + media_ids after config load (T-123: keep after model check). |
| T-113..T-127 | TODO | tiers 2-9 |

## Tier 0 gate (inspector, 2026-10-30): PROCEED (0 P0/P1)
Codex gate failed to run (invocation error); inspector used. Inputs for T-112 / follow-ups:
- P2 form_validation: Python never passes user_msg; Java save() always adds it (ActionSupport.java:89, FormValidationAction.java:92).
- P2 CallbackAction.java:49 metadataLog init null; Python [] -> init empty list.
- P2 ScheduleAction.java:62 dataLog init null; Python {} -> init empty map.
- P3 PromptAction.java:125 extras order: llm_call_id belongs after time_elapsed.
- P3 PromptAction.java:44 media_ids read before FAQ gate; Python null until config loaded.
- P3 DbPayload list += str extends char-wise in Python (edge; deliberate divergence or port).
- P3 findLlmSecret/findLlmModel .first() vs Python .get() MultipleObjectsReturned (accept/document).

## Tier 1 gate (inspector, 2026-10-30): BLOCK -> fixed (cycle 1)
- P1 fixed: LlmHttp maps any real >=400 response to 'Internal Server Error' (Python RetryClient raise_for_status before status_code set); transport failures keep 503/408/500. LlmHttpTest updated; kit llm-vector-clients R3 c4 reworded (outbound-clients R1 c4 was right).
- P3 fixed: form_validation no longer logs exception (Python never passes it).
- Open P3: QdrantClient non-2xx/non-JSON error text should match aiohttp 3.9.5 ClientResponseError str (`<status>, message='<phrase>', url=URL('<url>')`); LlmSecrets bad-Fernet-token text differs (Python '' ) - accept or map; T-123 keep media_ids read after secret lookup + model check.
- Never log LlmSecrets.secret() map (holds plaintext api_key).
