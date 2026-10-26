---
created: "2026-10-26T14:07:45Z"
last_edited: "2026-10-26T14:38:10Z"
---
# Implementation Tracking: parity-harness

Build site: context/plans/build-site.md

| Task | Status | Notes |
|------|--------|-------|
| T-024 | DONE | fixture-schema.json/.md v1, placeholders inventory, schema validation test |
| T-025 | DONE | recorder.py opt-in plugin (TestClient/responses/aioresponses patched per test, Mongo before/after snapshots, canonical EJSON); validated with pytester+mongomock. BLOCKER: full recording run over 434 nodes needs a MongoDB (none on this machine) |
| T-041 | DONE | normalize.py: time-window volatility, indexed placeholders, {{BINARY}} token, CLI --validate; recorder normalizes by default |
| T-045 | DONE | Java parity package: Fixture/Loader/Placeholders/JsonMatcher/UpstreamStubs/CatalogSeeder/WrittenDocs/FixtureReplay + 3 synthetic fixtures; 28 tests; real fixtures still pending (no Mongo) |
| T-053 | DONE | ParityReplayTest @TestFactory over bundled + KAIRON_PARITY_FIXTURES dir; ReplayEndpoints maps settings URLs to stubs; time_elapsed/response_headers.date volatile; synthetic fixtures regenerated (master green again) |
