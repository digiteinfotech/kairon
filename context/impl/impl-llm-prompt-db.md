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
| T-107..T-127 | TODO | tiers 1-9 |
