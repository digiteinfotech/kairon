---
created: "2026-10-26T13:46:03Z"
last_edited: "2026-10-26T14:04:01Z"
---
# Implementation Tracking: dispatch-and-logging

Build site: context/plans/build-site.md

| Task | Status | Notes |
|------|--------|-------|
| T-028 | DONE | prompt/database unregistered (classes kept); rephrase path removed; log fields per settings |
| T-038 | DONE | Log builder: declared order, nulls omitted, trigger_info as-is or default (catch-all always default like Python), request_id = header |
| T-039 | DONE | FailureMail async via SmtpMailer; action_failure.html template; bot name lookup; EmailAction/ParallelAction/Razorpay still on legacy 4-arg call (follow-up); EMAIL_SENDER_* settings not yet in application.yml/CONFIG.md (follow-up) |
