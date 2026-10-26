## Agent: library-landscape
Caveat: thin search results; several points rest on general knowledge, flagged with lower confidence; no adoption metrics fetched.

### Q5a Micronaut 4.x + native-image + Mongo sync + Serde
- Mongo module `io.micronaut.mongodb:micronaut-mongo-sync` registers blocking MongoClient; config via `mongodb.uri` + nested cluster/connectionPool/socket/server/ssl; customizers via `MongoClientSettingsBuilderCustomizer`. [source: https://micronaut-projects.github.io/micronaut-mongodb/latest/guide/] Confidence: high.
- POJO mapping: `@Serdeable` + serialization-bson/jackson features, `@BsonCreator`/`@BsonProperty`; `@BsonDiscriminator` needs `mongodb.package-names` + `@Introspected`. [source: https://guides.micronaut.io/micronaut-mongodb-synchronous-gradle-java/] Confidence: high.
- Dynamic tracker/events JSON: keep as `org.bson.Document`/`Map<String,Object>` to avoid POJO codec reflection (inference). Confidence: med.
- Native build: `./gradlew nativeCompile`, recent GraalVM; native binary behaves same as JVM. Confidence: high.
- Reflection config: Micronaut compile-time via `@Introspected`/`@Serdeable`; hand JSON under `META-INF/native-image/<group>/<artifact>/`; tracing agent can generate from tests; prefer `@ReflectionConfig`/`@TypeHint`. [source: https://guides.micronaut.io/latest/micronaut-graalvm-reflection.html] Confidence: high.
- Mongo driver native gotchas: driver ships reachability metadata (JAVA-5407); skip CSFLE/mongodb-crypt; verify SRV DNS, TLS, compression in real native run. Confidence: low-med.

### Q5b Outbound HTTP
- Declarative `@Client` + `@Retryable` compile-time, no reflection; timeouts via HttpClientConfiguration. [source: https://docs.micronaut.io/4.3.7/api/io/micronaut/http/client/annotation/package-summary.html] Confidence: med-high.
- Action server URLs/headers/body/timeouts come from DB config at runtime -> declarative poor fit; inject low-level `HttpClient`, `HttpRequest.create(method, uri).headers(...)`; Micronaut lacks true per-request read-timeout -> cache clients per timeout bucket (verify). Confidence: med.
- `java.net.http.HttpClient`: per-request timeouts, native-fine, no Micronaut filters/tracing; hand-rolled retries. Confidence: low.
- Parity: verify redirect-following and TLS verification match Python (aiohttp/httpx).

### Q5c Templating / Python expressions
- Hand-roll `${slot}`/`{slot}` interpolator (~100 lines regex) for exact parity incl. escaping and missing-key behaviour; native-safe. Confidence: med-high.
- Jinjava (HubSpot) reflection+EL, needs native metadata [source: https://central.sonatype.com/artifact/com.hubspot.jinjava/jinjava/]; Pebble; JTE/JStachio/Rocker compile-time (bad for runtime user templates). Confidence: low-med.
- GraalPy supports native-image [source: https://graalvm.org/dev/reference-manual/python/native-applications] but avoid: large binary, slow startup, CPython gaps, sandbox risk. Verdict: delegate pyscript over HTTP. Confidence: med-high.

### Q5d Email + JSON logging
- `io.micronaut.email:micronaut-email-javamail` (Jakarta Mail, native support documented) [source: https://docs.micronaut.io/5.1.x/email/]; `javamail.properties.mail.smtp.*`; test STARTTLS vs SSL + auth in native. Confidence: med.
- JSON logging: logstash-logback-encoder + Logback ConsoleAppender to stdout; AsyncAppender/RollingFileAppender had native issues. [source: https://mailman.qos.ch/pipermail/logback-dev/2022-November/013193.html] Confidence: med.

### Open questions
1. Python per-action HTTP timeouts and retry counts?
2. Exact placeholder syntax/edge cases: `${x}`, `{x}`, `{{x}}`, nested, missing-key?
3. Mongo SRV/TLS/CSFLE/compression in use?
4. Python SMTP mode (STARTTLS/SSL, auth, attachments)?
5. GraalVM + Micronaut Gradle plugin version compatibility (module 6.2.0 vs Micronaut 4.10)?
6. Adoption metrics missing.
