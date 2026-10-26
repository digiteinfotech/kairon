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
