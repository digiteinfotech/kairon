## Agent: best-practices
Caveat: thin search coverage; "knowledge-based" items unsourced.

### Q1 Per-test JSON fixtures from pytest (Confidence: med)
1. Recommended: conftest.py autouse recorder fixture, no test edits. Wrap `responses.RequestsMock._on_request` and `aioresponses.aioresponses._request_mock`; `responses.calls` CallList has request url/method/body/headers + response status/text; `aioresponses.requests` dict keyed (method, URL). Capture per test: Mongo snapshot before (seed), inbound request (wrap TestClient.post), upstream hits (wrapped mocks), response body, Mongo snapshot after (expected logs). Write fixtures/<nodeid>.json; use `pytest_runtest_makereport` to skip failing tests. `bson.json_util.dumps(..., CANONICAL_JSON_OPTIONS)` for round-trip.
2. pytest-recording/vcrpy record real traffic; don't capture hand-written mocks; not a fit. [source: https://libraries.io/pypi/vcrpy]
3. `responses._recorder` records real calls only.
4. Java side: JUnit @TestFactory/@ParameterizedTest over fixture files: seed, WireMock stubs, POST, JsonUnit assert ignoring timestamp, compare WireMock journal to recorded hits, diff Mongo docs ignoring _id/timestamp.
Rollout: pytest --collect-only to size 434 IDs; run recorder; triage exact vs normalisation-needed (UUIDs, time); freeze time (freezegun/time-machine) for determinism.

### Q2 Fernet on JVM (Confidence: high API, med maintenance)
- fernet-java8 (com.macasaet.fernet:fernet-java8:1.4.2): pure Java, zero deps, validated against spec. DEFAULT TTL 60s via Validator -> Conflict: Python Fernet.decrypt without ttl has no expiry; override getTimeToLive. [source: https://github.com/l0s/fernet-java8]
- io.github.atkawa7:fernet exists, unevaluated.
- Hand-roll (~40 lines): `0x80 || ts(8 BE) || IV(16) || AES-128-CBC/PKCS5 || HMAC-SHA256(32)`; key = 32-byte urlsafe-b64, first 16 signing, last 16 encryption; token urlsafe-b64 with padding. JDK javax.crypto only; native-simple. Confidence high.
- Verify: spec vectors https://github.com/fernet/spec (generate.json, verify.json, invalid.json); Python mints with kairon keys; cross-decrypt both ways; future timestamp (60s skew), expired, bad padding, invalid-key path (Python catches InvalidToken), unicode + empty plaintext.

### Q3 json.dumps vs Jackson; Python repr (Confidence: med-high)
| Item | Python | Jackson | Fix |
| Separators | ", " / ": " | "," / ":" | custom Separators if bytes compared |
| Non-ASCII | ensure_ascii \uXXXX surrogate pairs | raw UTF-8 | ESCAPE_NON_ASCII; hex case may differ |
| Floats | 1.0 stays, 1e16 -> 1e+16, shortest repr | Double.toString 1.0E16 | compare numerically or custom serializer |
| NaN/Inf | bare NaN (invalid JSON) | quoted strings | ignore |
| Key order | insertion | LinkedHashMap insertion | use LinkedHashMap/Document; disable ORDER_MAP_ENTRIES_BY_KEYS |
Python repr (str(dict)) into Mongo/log fields: single quotes (double if contains '), True/False/None, Decimal('1'), datetime.datetime(...). Java needs explicit PyRepr.of(Object) for Map/List/String/Boolean/null/numbers/ObjectId/datetime, unit-tested against captured Python strings. Grep Python for str()/repr()/f-string of dicts persisted to Mongo. Conflict: Map/Document fine for storage; str() paths need insertion-order Map (Document is LinkedHashMap, OK).

### Q4 Micronaut test suite in-memory + real Mongo (Confidence: med)
- Micronaut Test Resources auto-starts Mongo via Testcontainers when driver on classpath and no mongodb.uri. [source: https://docs.micronaut.io/5.1.x/mongodb/]
- Structure: abstract AbstractActionParityTest (all cases, talks to catalog interface + HTTP client); InMemoryParityTest @MicronautTest(environments="inmem") with @Requires(env) bean; MongoParityTest environments="mongo" + Test Resources. BSON assert: Document.toJson(RELAXED) + JsonUnit whenIgnoringPaths("_id","timestamp"). Drop collections per test @BeforeEach; separate DB names for parallel.

### Q5 Native + outbound HTTP (Confidence: med)
- Micronaut HttpClient Netty, native-ready; HttpClientConfiguration: followRedirects, read timeout, read-idle. [source: https://docs.micronaut.io/latest/api/io/micronaut/http/client/HttpClientConfiguration]
- SECURITY: GHSA-q6gh-6v2r-hjv3: DefaultHttpClient forwarded Authorization/Cookie/Proxy-Authorization across domains on redirect, no max redirect count. Affected 4.x < 4.10.24, 5.x < 5.0.1. Pin >= 4.10.24. [source: https://advisories.gitlab.com/maven/io.micronaut/micronaut-http-client/GHSA-q6gh-6v2r-hjv3/] Conflict: port is on 4.10.22 -> vulnerable, bump.
- aiohttp semantics: allow_redirects=True, max_redirects=10; 301/302/303 POST->GET drop body, 307/308 keep; strips Authorization cross-origin (verify pin); ClientTimeout(total=N) hard wall-clock cap incl connect+redirects+body, default 300s. Micronaut has no single total timeout -> wrap in .timeout()/orTimeout. JDK HttpClient: per-request timeout bounds headers not body; NORMAL never https->http; 5 hop cap.
- Recommendation: stay with Micronaut client, disable auto-follow, own explicit redirect loop (10 hops, method rewrite), keep TLS verification on.

### Open questions
1. Exact Micronaut patch version (4.10.22 < 4.10.24 fix).
2. Does Python pass ttl= to Fernet.decrypt?
3. Where Python stringifies dicts/exceptions into Mongo fields.
4. aiohttp pin's cross-origin Authorization stripping.
5. freezegun/time-machine in Python tests?
6. How pytest seeds Mongo.
7. APScheduler pickle out of scope here.
8. fernet-java8 release recency.
