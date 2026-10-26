---
created: "2026-10-26T14:07:45Z"
last_edited: "2026-10-26T14:38:10Z"
---
# Implementation Tracking: events-schedule-api

Build site: context/plans/build-site.md

| Task | Status | Notes |
|------|--------|-------|
| T-026 | DONE | pyscript + flow reference job docs captured via real ActionSchedule path on mongomock; byte-stable; decoded view + equivalent_schedule_request |
| T-027 | DONE | ScheduleActionRequest (pydantic v1), 8 fields, strict; from_payload -> AppException -> 200/422 envelope; T-042 must call from_payload, not declare as FastAPI body |
| T-042 | DONE | POST /api/events/schedule/action; build_schedule_action_job shared in kscheduler.py; from_payload parsing; duplicate -> 200/422 envelope; pyscript job_state byte-identical to reference, flow structurally equal (pickle memo quirk) |
| T-050 | IN PROGRESS | w4-python agent (worktree agent-a39f817e3f9af1443, branch w4-python) — not merged at cutoff |
| T-051 | IN PROGRESS | same packet |
| T-052 | IN PROGRESS | same packet |
