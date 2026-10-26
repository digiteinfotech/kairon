---
created: "2026-10-26T13:46:03Z"
last_edited: "2026-10-26T13:46:03Z"
---
# Implementation Tracking: config-and-deploy

Build site: context/plans/build-site.md

| Task | Status | Notes |
|------|--------|-------|
| T-001 | DONE | Python env names/defaults, DATABASE_URL default DB kairon, CONFIG.md table + test; 64MB max-request/buffer size needs human sign-off |
| T-002 | DONE | http-client constraints >=4.10.24 + checkAdvisories task; platform stays 4.10.22 (artifact not on classpath) |
| T-003 | DONE | uuidRepresentation PYTHON_LEGACY unless URL overrides; codec round-trip test |
| T-004 | DONE | @ExecuteOn(BLOCKING) on WebhookController; virtual-thread test |
| T-016 | DONE | max-request-size + max-request-buffer-size 64MB; Jsons maxStringLength lifted; 20MB test |
