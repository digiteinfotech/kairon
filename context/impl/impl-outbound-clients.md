---
created: "2026-10-26T13:46:03Z"
last_edited: "2026-10-26T14:26:54Z"
---
# Implementation Tracking: outbound-clients

Build site: context/plans/build-site.md

| Task | Status | Notes |
|------|--------|-------|
| T-017 | DONE | Manual redirect loop: 10 hops, 301/302/303->GET, 307/308 keep, cross-origin credential strip, TLS on |
| T-018 | DONE | requests-style form/query encoding; JSON no charset; requote spaces; c6 downstream sensitivity still human review |
| T-019 | DONE | One multipart request per media file (kit corrected to Python) |
| T-020 | DONE | Raising exchange + evaluator client stub tests |
| T-021 | DONE | Pyscript client stub tests |
| T-022 | DONE | SmtpMailer (angus-mail), GreenMail tests, STARTTLS semantics |
| T-023 | DONE | Email HTML templates copied from template/emails; golden tests vs Python functions |
| T-033 | DONE | Whole-exchange deadline from ACTION_SERVER_REQUEST_TIMEOUT; null/null on transport failure; no retry; OK set; tests |
| T-033b | DONE | Transport errors now 503/408/500 with Python error text; kit R1 corrected. OPEN [GAP] from gate: any non-2xx must become 500/None; non-JSON 2xx body as text (fix cycle) |
