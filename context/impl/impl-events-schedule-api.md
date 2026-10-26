---
created: "2026-10-26T14:07:45Z"
last_edited: "2026-10-26T14:07:45Z"
---
# Implementation Tracking: events-schedule-api

Build site: context/plans/build-site.md

| Task | Status | Notes |
|------|--------|-------|
| T-026 | DONE | pyscript + flow reference job docs captured via real ActionSchedule path on mongomock; byte-stable; decoded view + equivalent_schedule_request |
| T-027 | DONE | ScheduleActionRequest (pydantic v1), 8 fields, strict; from_payload -> AppException -> 200/422 envelope; T-042 must call from_payload, not declare as FastAPI body |
