---
created: "2026-10-26T14:07:45Z"
last_edited: "2026-10-26T14:07:45Z"
---
# Implementation Tracking: parity-harness

Build site: context/plans/build-site.md

| Task | Status | Notes |
|------|--------|-------|
| T-024 | DONE | fixture-schema.json/.md v1, placeholders inventory, schema validation test |
| T-025 | DONE | recorder.py opt-in plugin (TestClient/responses/aioresponses patched per test, Mongo before/after snapshots, canonical EJSON); validated with pytester+mongomock. BLOCKER: full recording run over 434 nodes needs a MongoDB (none on this machine) |
