---
created: "2026-10-26T13:46:03Z"
last_edited: "2026-10-26T13:46:03Z"
---
# Implementation Tracking: templating-and-secrets

Build site: context/plans/build-site.md

| Task | Status | Notes |
|------|--------|-------|
| T-005 | DONE | PyRepr + Python json.dumps in Jsons; CPython golden tests |
| T-006 | DONE | Fernet spec vectors + Python cross-decrypt (live via .venv, skips if absent) |
| T-007 | DONE | JWT structure tests; header alg,typ (kit corrected); store-page fallback 15 |
| T-008 | DONE | sender_id Fernet decrypt when valid token |
| T-009 | DONE | latest_message param falls through to literal value (kit corrected) |
| T-010 | DONE | context key order; key_vault {} unless requested; bot added per caller (kit corrected) |
