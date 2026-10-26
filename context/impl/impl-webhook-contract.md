---
created: "2026-10-26T13:46:03Z"
last_edited: "2026-10-26T14:04:01Z"
---
# Implementation Tracking: webhook-contract

Build site: context/plans/build-site.md

| Task | Status | Notes |
|------|--------|-------|
| T-011 | DONE | TrackerState defaults paused/active_loop/active_form/latest_action_name/stack |
| T-012 | DONE | 500 on missing tracker/sender_id; 200 error envelope; catch-all keeps prior utterances (kit corrected); next_action stripped not lowercased |
| T-013 | DONE | WebhookTest rewritten to Python contract (41 tests) |
| T-014 | DONE | UUID4 request id when header absent; echoed; thread-local via request attribute |
| T-015 | DONE | Full secure-header set from captured Python responses |
| T-032 | DONE | Health bodies + no-auth webhook tests |
| T-035 | DONE | Starlette-style CORS in SecurityFilter from ALLOWED_ORIGIN; Micronaut CORS off; localhost-pass-through=true needs human review |
