---
created: "2026-10-26T13:46:03Z"
last_edited: "2026-10-26T14:19:26Z"
---
# Implementation Tracking: dispatch-and-logging

Build site: context/plans/build-site.md

| Task | Status | Notes |
|------|--------|-------|
| T-028 | DONE | prompt/database unregistered (classes kept); rephrase path removed; log fields per settings |
| T-038 | DONE | Log builder: declared order, nulls omitted, trigger_info as-is or default (catch-all always default like Python), request_id = header |
| T-039 | DONE | FailureMail async via SmtpMailer; action_failure.html template; bot name lookup; EmailAction/ParallelAction/Razorpay still on legacy 4-arg call (follow-up); EMAIL_SENDER_* settings not yet in application.yml/CONFIG.md (follow-up) |
| T-047 | DONE | messages[] on pyscript/live_agent/callback logs |
| T-048 | DONE | http_action events[] sub-docs in Python order/keys; time_elapsed = api+slots+pyscript+compose with Python units; fail_reason PyRepr; EmailAction/ParallelAction/Razorpay now send full failure mail (T-039 follow-up). HUMAN REVIEW: Python-parity logs embed decrypted key_vault in compose/slot/pyscript event data. |
