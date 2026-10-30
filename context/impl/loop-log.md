# Loop Log

Build site: context/plans/build-site.md

### Iteration 1 (Wave 1, Tier 0 part 1) — 2026-10-26T13:46:03Z
- Packets: config(T-001,002,003,016) contract(T-004,008,011,012,013,014,015,032) templating(T-005,009,010,021,023) http(T-017..020,022) crypto-actions(T-006,007,028..031) python(T-024..027 still running).
- 28/32 Tier 0 tasks DONE, merged to master ef3d6117. Build P, Tests P (147).
- Kit corrections mid-wave (code already matched Python): catch-all keeps prior utterances; google website keyless-only; JWT header alg,typ; latest_message param literal; media one request per file; context bot per caller. Build-site matrix resynced.
- Merge: build.gradle conflict (constraints vs mail deps) resolved keeping both.
- Next: T-024..027 (python packet), then Tier 1 frontier T-033..040,043,044.

### Iteration 2 (Wave 2, Tier 1 part 1) — 2026-10-26T14:05:19Z
- Packets: config(T-033,034,035) actions(T-040,044) logging(T-036,037,038,039,043). 10/13 Tier 1 DONE, merged to master 93347843. Build P, Tests P (197).
- Kit corrected mid-wave: parallel pre-record = request_id + model defaults (not empty).
- Follow-ups: EmailAction/ParallelAction/RazorpayAction still call legacy failureMail (no slots/stack); EMAIL_SENDER_* + EMAIL_TEMPLATES_ACTION_FAILURE not in application.yml/CONFIG.md; CORS localhost-pass-through needs human review.
- Note: coordinator commit 804a36e6 (impl tracking) also committed the user's pre-staged deletion of kairon-action/ (no pathspec). Matches staged intent; revertible.
- Waiting: python packet T-024..027 (Tier 0), then T-041,042,045.

### Iteration 3 (Wave 1 python packet landed) — 2026-10-26T14:07:45Z
- T-024,025,026,027 DONE (cherry-picked de2b2b31 -> 76be2453; worktree was on origin/master). Tier 0 complete 32/32.
- Python env: /Data/projects/kairon/.venv310 (uv sync --frozen, py3.10). Shared .venv unusable for kairon.
- BLOCKER for replay tier: no MongoDB -> fixtures not recorded yet.
- Tier 0 gate: Codex review pending.

### Iteration 4 (Wave 3 part 1) — 2026-10-26T14:19:26Z
- T-046,055,047,048 DONE + follow-ups (email SMTP config in application.yml/CONFIG.md; full failure mail in Email/Parallel/Razorpay). Merged 40fa2f33, c260b064. Tests P (214).
- Kit corrected: outbound R1 c2/c3/c5 — Python sets 503/408/500 on transport errors (rest_client.py:89-101); port returns null -> new [GAP], fix dispatched (w3-status).
- Tier 0 gate: Codex failed on 22k-line diff; ck:inspector running as fallback.
- Running: w3-python (T-041,042), w3-replay (T-045), w3-status. Deferred: T-054 load test until machine quieter.
- HUMAN REVIEW items accumulating: key_vault in logs, compose SECRET_KEY must match kairon-api, CORS localhost-pass-through, docker build unverified.

### Iteration 5 (Wave 3 complete; Tier 0 gate) — 2026-10-26T14:26:54Z
- T-041,042,045 DONE + T-033 follow-up. Merged 9269357a, c594d3ff, cee3461a. Tier 0 32/32, Tier 1 13/13, Tier 2 4/10.
- Gate (ck:inspector fallback): REVISE — 0 P0, 5 P1 (mask strategy, media download from cloud storage, non-2xx -> 500/None, intent fallback rules, ScheduleAction job-store write), 12 P2, 12 P3. Findings: context/impl/impl-review-findings.md.
- P1 F-001..F-004 verified against Python (live check: 404 -> (None, 500)); kits corrected (+4 criteria, now 405). F-005 is T-049 (next wave). Fix cycle 1 dispatched next.

### Iteration 6 (Wave 4 partial; SESSION CUT OFF by usage limit) — 2026-10-26T14:38:10Z
- Merged: T-049 (63aee133), T-053 + master red fix (0c0b78db). Master at 0c0b78db should be green (261 tests on the replay branch); re-run `cd action-server && ./gradlew test` to confirm.
- STILL RUNNING at cutoff (will commit on their own branches in .claude/worktrees/): w4-fix (branch w4-fix: gate P1 fixes F-001..F-004), w4-python (branch w4-python: T-050, T-051, T-052). Merge them with `git merge <branch> --no-edit`, run the Java suite and the Python modules with .venv310, then `git worktree remove <path> --force && git branch -D <branch>`.
- Progress: 51/96 tasks DONE (Tier 0 32/32, Tier 1 13/13, Tier 2 6/10). Tier 0 gate: inspector REVISE (5 P1) -> fix cycle 1 in flight (w4-fix); after merge re-run the gate (Codex fails on diff size; use ck:inspector on the fix diff) before Tier 3.
- Remaining frontier after merges: T-054 (load test; run when machine idle), Tier 3 verification tasks T-056..T-092 (need real fixtures -> need a MongoDB to run the recorder: `KAIRON_RECORD_FIXTURES=1 .venv310/bin/pytest tests/integration_test/action_service_test.py ...`), Tier 4 T-093..T-096.
- Resume with /ck:resume (or /ck:make) once the two branches are merged.
- HUMAN REVIEW backlog: key_vault secrets embedded in Python-parity log events; compose SECRET_KEY must equal kairon-api's; CORS localhost-pass-through; docker image build unverified (daemon not usable); 64MB request ceiling; failure-mail wording; events endpoint auth posture; P2 findings in impl-review-findings.md (decryptMaybe sends ciphertext upstream on key mismatch; https-stub-base settable from env in prod).
- Note: commit 804a36e6 swept the user's pre-staged deletion of kairon-action/ into the tracking commit; revert that commit's kairon-action hunk if the Rust port should stay.

### Iteration (llm-prompt-db) 1 — 2026-10-30
- T-100..T-106: DONE (tier 0, 4 packets, merged 3188a78f). Files: ActionSettings, application.yml, catalog/*, TokenTruncator, ActionSupport.logRecord, FaqGate, DbPayload, PromptParams + tests. Build P, full suite P (0 fail). Next: tier 1 T-107..T-112. Open: T-112 review of other actions' null extras; Mongo live contract run; tier-gate review pending.

### Iteration (llm-prompt-db) 2 — 2026-10-30
- T-107..T-112: DONE (tier 1, 4 packets, merged). Build P, full suite P (0 fail). Open: kit conflict LLM R3 c4 vs outbound R1 (404 phrase); tier 1 gate pending. Next: tier 2 T-113..T-115 after gate.

### Iteration (llm-prompt-db) 3 — 2026-10-30
- T-113..T-116: DONE (tier 2, 4 packets, merged; PromptAction source-registry conflict resolved by hand). Build P, full suite P (0 fail). Tier 1 gate fix e8f255db (P1 LLM >=400 -> Internal Server Error). Next: tier 2 gate, then tier 3 T-117..T-119.

### Iteration (llm-prompt-db) 4 — 2026-10-30
- T-117,T-118: DONE (tier 3, 1 packet, merged). Tier 2 gate fixes bff13524 (nested no-is_success AttributeError; schema text; swap rules). Build P, full suite P. Next: T-119, T-120 (tier 4).

### Iteration (llm-prompt-db) 5 — 2026-10-30
- T-119,T-120: DONE (tier 4, 2 packets, merged). Build P, full suite P (484 tests). Gate for tiers 3+4 pending. Next: T-121, T-122 (tier 5). Also: agent_action parity fixes 772f1f19; second pass found non-dict body repr + falsy output + token claims (deferred).

### Iteration (llm-prompt-db) 6 — 2026-10-30
- T-121,T-122: DONE (tier 5, 2 packets, merged). Build P, full suite P (495 tests). Tier 3+4 gate PROCEED e43b1c20. Next: tier 5 gate, then T-123 (PromptAction rewrite), T-124 (tier 6).

### Iteration (llm-prompt-db) 7 — 2026-10-30
- T-123,T-124: DONE (tier 6, 2 packets, merged clean). Build P, full suite P (509 tests). Tier 5 gate PROCEED. Next: tier 6 gate, then T-125 (prompt output/log parity), T-126 (adapter removal; needs T-107,T-124,T-125), T-127 (e2e).

### Iteration (llm-prompt-db) 8 — 2026-10-30
- T-125: DONE (tier 7, merged clean). Build P, full suite P (527 tests). Tier 6 gate PROCEED. Next: T-126 (remove adapter leftovers), T-127 (e2e).
