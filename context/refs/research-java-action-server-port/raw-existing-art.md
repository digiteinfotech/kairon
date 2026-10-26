## Agent: existing-art
Caveat: search snippets only, no full page fetches; adoption metrics unavailable.

### Q6a Parity / characterization patterns
- Characterization / golden master: record legacy output per input, assert new reproduces it; normalize timestamps, generated IDs, randomness; investigate every diff before re-recording. [source: https://en.wikipedia.org/wiki/Characterization_test] [source: https://dev.to/rnowif/the-blind-golden-master-67h] Confidence: high.
- Diffy (Twitter, archived) / Opendiffy: proxy multicasts each request to candidate, primary, secondary; primary-vs-secondary diff measures noise, subtracted from candidate-vs-primary. Fits HTTP responses; blind to side effects (Mongo, outbound, email). [source: https://blog.x.com/engineering/en_us/a/2015/diffy-testing-services-without-writing-tests] Confidence: high.
- Shadow testing / traffic mirroring: mirror prod traffic to new system, compare, cut over. [source: https://microsoft.github.io/code-with-engineering-playbook/automated-testing/shadow-testing/] Confidence: high.
- "Tap compare" pattern (title only). [source: https://rednafi.com/system/tap-compare-testing/] Confidence: low.

### Q6b Rasa action server protocol
- Request: `next_action`, `sender_id`, `tracker` (slots, latest_message, events), `domain`, `version`. Rasa SDK >= 3.9.0 caches domain and uses `domain_digest`; request may omit `domain`. [source: https://rasa.com/docs/rasa-pro/action-server/actions] [source: https://rasa.com/docs/reference/api/pro/action-server-api/] Confidence: high.
- Response: `{"events":[...], "responses":[{"text":...}]}`. Slot event `{"event":"slot","timestamp":null,"name":"x","value":...}` with explicit `null` timestamp (parity-sensitive). Confidence: high.
- Full event list/shapes not retrieved.
- Non-Python ports: JRasa (Java SDK for Rasa 3.x, SpringBoot demo) [source: https://github.com/uncle-lv/JRasa] Confidence: med; rbajek rasa-java-sdk outdated. No Kotlin port. Contract is a single `/webhook` POST, custom impl viable.

### Q6c Python-to-JVM rewrites
- No specific 2024+ post found. One note: Java+Python run in parallel on live traffic for weeks, diffed at seams; unit tests gave little signal; most diffs from undocumented defaults (empty arrays serialized differently, timeout inheritance, error message text clients parse); ignore generated IDs, keep ordering + semantic errors. [source: https://agent.kombai.com/kombai-inspiration-library/app-pages/blog-posts/web/65/index.html] Confidence: low.
- Lesson: check empty/null/default serialization and error-message text explicitly.

### Q6d Side-effect parity tooling
- WireMock record/playback: proxy, writes stub mappings, verifies received requests -> point both impls at WireMock, diff request journals. [source: https://wiremock.org/docs/record-playback/] Confidence: high.
- JSON compare: JSONassert (STRICT/LENIENT) [source: https://howtodoinjava.com/java/library/jsonassert-tutorial]; JsonUnit (ignore paths, placeholders) [source: https://github.com/lukas-krecan/JsonUnit]. Confidence: high.
- Mongo: ObjectId embeds timestamp; strip `_id` and time fields; export to JSON per impl, compare with JsonUnit. No dedicated diff tool. Confidence: med.

### Open questions
1. Full Rasa event list and shapes.
2. Does Kairon Python server use `domain_digest`/domain caching?
3. JRasa maturity (do not rely on it).
4. Canonical 2024+ Python-to-JVM post.
5. Hoverfly/MockServer vs WireMock for two-impl diff.
6. Opendiffy non-idempotent POST replay — likely needs custom harness diffing response + Mongo + WireMock journal.
