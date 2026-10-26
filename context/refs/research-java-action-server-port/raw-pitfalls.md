## Agent: pitfalls
Caveat: search quality poor; only PyMongo UUID table verified from fetched page; rest knowledge-based.

### Q1 APScheduler 3.x MongoDBJobStore (Confidence: med)
- Doc: `_id` = job id string (not ObjectId); `next_run_time` float UTC epoch seconds (null if paused), indexed; `job_state` = Binary(pickle.dumps(job.__getstate__(), HIGHEST_PROTOCOL)). [source: https://apscheduler.readthedocs.io/en/3.x/modules/jobstores/mongodb.html]
- __getstate__: {version=1, id, func (textual "module:callable" ref), trigger (pickled DateTrigger/CronTrigger with tz objects), executor, args, kwargs, name, misfire_grace_time, coalesce, max_instances, next_run_time (tz-aware datetime)}.
- Java writer technically possible via net.razorvine:pickle (protocol 2, limited class construction); must hand-craft GLOBAL/REDUCE/BUILD for apscheduler.triggers.date + tz classes; no documented working case. Risks: silent break on APScheduler/tz upgrade (zoneinfo vs pytz pickle differently); corrupted job_state -> _reconstitute_job removes job; unpickling executes arbitrary code (security surface).
- Instead: (A) thin Python shim/sidecar owning scheduling, Java calls over HTTP or writes neutral outbox collection Python polls; (B) replace APScheduler with Java scheduler (JobRunr, Quartz-Mongo, db-scheduler) + one-time migration. If both must coexist during migration, shim is only parity-safe path. Recommendation: do NOT write pickle from Java.

### Q2 Mongo timestamp/ObjectId/UUID parity
- PyMongo default UuidRepresentation UNSPECIFIED (encoding uuid.UUID raises). STANDARD = subtype 4; PYTHON_LEGACY = subtype 3 RFC byte order; JAVA_LEGACY = subtype 3 reversed bytes. [source: https://www.mongodb.com/docs/languages/python/pymongo-driver/current/data-formats/uuid/] Confidence: high.
- mongoengine connect() defaults uuidRepresentation=pythonLegacy (~0.20+, deprecation warning) -> existing UUIDField data likely subtype 3 standard order. Java: use UuidRepresentation.PYTHON_LEGACY (byte-identical); never JAVA_LEGACY. Java 5.x default UNSPECIFIED throws -> set uuidRepresentation=pythonLegacy. Mixed subtypes need explicit BsonBinary. uuid7 stored as .hex strings -> irrelevant. Confidence: med; verify subtype on real doc.
- Dates: BSON int64 UTC ms; PyMongo truncates micros; naive utcnow stored as UTC; Java Instant/Date same ms; truncate Instant.now() to MILLIS for comparisons; PyMongo reads naive (tz_aware=False). Don't let Serde/Jackson write dates as ISO strings/epoch numbers; use BSON codecs. Confidence: high.
- Field order: mongoengine declared fields in declaration order, then dynamic. Document (LinkedHashMap) preserves insertion order; POJO codec by property order. `_cls` only with allow_inheritance; check. Confidence: med.
- ObjectId: same 12-byte format, compatible not identical.

### Q3 uuid7 (Confidence: high layout, med libs)
RFC 9562: 48-bit unix ms, 4-bit version 0111, 12-bit rand_a, 2-bit variant 10, 62-bit rand_b. Python uuid6/uuid_utils/3.14 stdlib follow it; older uuid6 differed in rand_a counter. JVM: com.github.f4b6a3:uuid-creator UuidCreator.getTimeOrderedEpoch() or ~10 lines hand-rolled (SecureRandom only, native-friendly). Python .hex = 32 lowercase no dashes; Java UUID.toString().replace("-",""). Case matters for Mongo string _id lookups and APScheduler job ids.

### Q4 Micronaut 4 + Netty, self-loopback (Confidence: med; defaults low-med)
- Never block Netty event loop; Micronaut 4 BlockHint detects BlockingHttpClient on event loop. [sources: https://github.com/micronaut-projects/micronaut-core/issues/3694, https://docs.micronaut.io/4.4.8/api/io/micronaut/http/client/netty/BlockHint.html]
- Annotate blocking controllers @ExecuteOn(TaskExecutors.BLOCKING); on Java 21 set micronaut.executors.blocking.type=virtual -> blocking HttpClient/Mongo/SMTP cheap; fan-out with StructuredTaskScope/CompletableFuture = asyncio.gather analogue. JDK 21 virtual-thread pinning in synchronized (Mongo sync, Jakarta Mail); JEP 491 in JDK 24+.
- Self-loopback is a smell; prefer in-process dispatch unless loopback is observable (audit logs/headers) -> keep for parity. If loopback: pooled low-level client, explicit read/connect timeouts; blocking pool must not be smaller than max fan-out (deadlock/starvation); virtual threads avoid.
- Defaults to verify (from memory): server max-request-size ~10MB (uvicorn/FastAPI unlimited -> large trackers may 413); multipart max-file-size 1MB; max header 8KB; client read-timeout 10s, connect-timeout ~10s (aiohttp total 300s); server idle-timeout ~5min (uvicorn keep-alive 5s); event-loop threads 2x cores; blocking pool fixed 2x cores with queue. Check https://docs.micronaut.io/latest/guide/configurationreference.html

### Q5 GraalVM native (Confidence: med)
- JWT: jjwt reflection + ServiceLoader, historically manual reflect-config [source: https://github.com/jwtk/jjwt/issues/637]; auth0 java-jwt Jackson reflection; Micronaut security uses nimbus-jose-jwt tested under native. Recommendation: nimbus via Micronaut security, or hand-roll HS256 with javax.crypto.Mac (~20 lines, zero native risk). Match PyJWT: header key order typ then alg, compact separators, exp as integer.
- Fernet: AES/CBC/PKCS5Padding + HmacSHA256 in SunJCE, native OK; keep algorithm names as string literals (constant-folding) [source: https://www.graalvm.org/jdk21/reference-manual/native-image/dynamic-features/JCASecurityServices/]. Confidence: high.
- Jakarta/Angus Mail: providers via META-INF/javamail.providers, mailcap, DataContentHandler (resource+reflection); need resource-config + reflection entries; "no object DCH for MIME type" typical failure; micronaut-email-javamail ships hints; test real send in native. STARTTLS/SSL via JDK default SSLContext fine. [source: https://encircle360.com/en/blog/graalvm-native-image-pitfalls]
- Mongo: mongodb+srv uses JNDI DNS (pain in older native); 5.x can use dnsjava on classpath; micronaut-mongodb module carries metadata; safest plain mongodb://host1,host2/?replicaSet=; TLS fine, truststore by path at runtime; optional compression/jnr probes tolerated.
- Run native tracing agent over full test suite.

### Q6 HTTP semantics parity (Confidence: med-high)
- Header casing: requests/aiohttp preserve; Netty preserves on HTTP/1.1; order differs; WireMock header match case-insensitive.
- User-Agent: requests `python-requests/X.Y.Z` [source: https://www.zenrows.com/blog/python-requests-user-agent]; aiohttp `Python/3.x aiohttp/3.x`; Micronaut none; JDK `Java-http-client/21`. Set explicitly if downstream inspects. Also Accept: */*, Accept-Encoding: gzip, deflate, Connection: keep-alive.
- Content-Type: requests/aiohttp json= -> `application/json` no charset; Micronaut may add `; charset=UTF-8`; form `application/x-www-form-urlencoded` no charset. Pin explicitly.
- Form nested dicts: requests data={'a':{'b':1}} -> `a=b` (lossy, iterates keys); lists -> repeated keys; True/False stringified; None dropped. aiohttp data=dict nested -> TypeError. Port quirk exactly.
- Query spaces: requests params / yarl -> `+` (quote_plus, keeps `~`); paths `%20`; Java URLEncoder `+` (keeps `*`, escapes `~`); UriBuilder/URI `%20`. Matters for byte-exact matching/signatures.
- Trailing slash: FastAPI 307 redirects to declared form; Micronaut doesn't redirect. Outbound: requests keeps URL as given, don't normalize.

### Open questions
1. Actual mongoengine uuidRepresentation in deployed config; check binary subtype on real docs.
2. Scheduler division of work if shim chosen; same jobs collection?
3. Does downstream inspect UA/charset/query encoding? Capture real outbound via mitmproxy/WireMock record.
4. Verify Micronaut 4.10 defaults (max-request-size, read-timeout, idle-timeout, blocking pool).
5. Virtual threads acceptable for deploy?
6. mongodb+srv in use?
7. `_cls` or DynamicDocument ordering reliance?
8. PyJWT claims/headers/alg used.
