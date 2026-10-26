package com.kairon.action.parity;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class UpstreamStubsTest {

    private static final HttpClient CLIENT = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(30)).build();

    private static final String FIXTURE = """
            {"schema_version": 1, "node_id": "n", "normalized": true,
             "mongo": {"available": false, "databases": [], "seed": {}, "written": {}},
             "exchanges": [],
             "upstream": [
               {"seq": 0, "client": "requests", "request": {"method": "POST", "url": "http://localhost:8081/hook/{{UUID_HEX:1}}?a=1",
                  "headers": [["User-Agent", "python-requests/2.32"], ["Content-Type", "application/json; charset=utf-8"],
                              ["Authorization", "Bearer {{JWT}}"], ["X-Kairon", "k1"]],
                  "body": {"encoding": "json", "value": {"id": "{{UUID_HEX:1}}", "n": 1}}},
                "response": {"status": 202, "headers": [["Content-Type", "application/json"], ["X-Reply", "r"]],
                  "body": {"encoding": "json", "value": {"ok": true}}}, "error": null},
               {"seq": 1, "client": "aiohttp", "request": {"method": "GET", "url": "http://other.test/down",
                  "headers": [], "body": {"encoding": "empty", "value": null}},
                "response": null, "error": {"type": "aiohttp.ClientConnectionError", "message": "down"}},
               {"seq": 2, "client": "requests", "request": {"method": "PUT", "url": "https://api.vendor.test/v1/x",
                  "headers": [], "body": {"encoding": "form", "value": {"a": "1", "b": 2}}},
                "response": {"status": 200, "headers": [], "body": {"encoding": "text", "value": "done"}}, "error": null}
             ]}
            """;

    private static HttpResponse<String> call(String method, String url, String contentType, String body, String... headers)
            throws IOException, InterruptedException {
        HttpRequest.Builder builder = HttpRequest.newBuilder(URI.create(url)).timeout(Duration.ofSeconds(60));
        if (contentType != null) {
            builder.header("Content-Type", contentType);
        }
        for (int i = 0; i + 1 < headers.length; i += 2) {
            builder.header(headers[i], headers[i + 1]);
        }
        builder.method(method, body == null ? HttpRequest.BodyPublishers.noBody() : HttpRequest.BodyPublishers.ofString(body));
        return CLIENT.send(builder.build(), HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void servesCannedRepliesRecordsHitsAndVerifiesClean() throws Exception {
        Fixture fixture = FixtureLoader.parse("stubs", FIXTURE);
        try (UpstreamStubs stubs = UpstreamStubs.start(fixture)) {
            String local = stubs.toStub("http://localhost:8081");
            String other = stubs.toStub("http://other.test");
            assertNotEquals("http://localhost:8081", local);
            assertNotEquals(local, other, "each http origin has its own stub");
            assertEquals("cfg http://localhost:8081/x", stubs.toRecorded("cfg " + local + "/x"));
            // An origin is not rewritten inside a longer authority.
            assertEquals("http://localhost:80811/x", stubs.toStub("http://localhost:80811/x"));

            String hex = "0f8fad5bd9cb469fa16570867728950e";
            HttpResponse<String> first = call("POST", local + "/hook/" + hex + "?a=1", "application/json",
                    "{\"n\": 1, \"id\": \"" + hex + "\"}", "Authorization", "Bearer aa.bb.cc", "X-Kairon", "k1");
            assertEquals(202, first.statusCode());
            assertEquals("{\"ok\":true}", first.body());
            assertEquals("r", first.headers().firstValue("X-Reply").orElse(null));

            assertThrows(IOException.class, () -> call("GET", other + "/down", null, null), "recorded error drops the connection");

            HttpResponse<String> third = call("PUT", stubs.httpsBase() + "/v1/x", "application/x-www-form-urlencoded", "a=1&b=2");
            assertEquals(200, third.statusCode());
            assertEquals("done", third.body());

            List<UpstreamStubs.Hit> hits = stubs.hits();
            assertEquals(3, hits.size());
            assertEquals(0, hits.get(0).seq());
            assertEquals("Bearer aa.bb.cc", hits.get(0).header("authorization"));
            List<String> problems = stubs.verify(new JsonMatcher(new Placeholders.Bindings()));
            assertTrue(problems.isEmpty(), String.join("\n", problems));
        }
    }

    @Test
    void reportsUncalledExtraAndDifferingCalls() throws Exception {
        Fixture fixture = FixtureLoader.parse("stubs", FIXTURE);
        try (UpstreamStubs stubs = UpstreamStubs.start(fixture)) {
            String local = stubs.toStub("http://localhost:8081");
            String hex = "0f8fad5bd9cb469fa16570867728950e";
            // Body id disagrees with the URL's UUID_HEX:1; header value differs; X-Kairon missing.
            call("POST", local + "/hook/" + hex + "?a=1", "text/plain", "{\"n\": 1, \"id\": \"1f8fad5bd9cb469fa16570867728950e\"}",
                    "Authorization", "Basic x");
            HttpResponse<String> extra = call("GET", local + "/unrecorded", null, null);
            assertEquals(599, extra.statusCode());

            List<String> problems = stubs.verify(new JsonMatcher(new Placeholders.Bindings()));
            String all = String.join("\n", problems);
            assertTrue(all.contains("unexpected upstream call GET http://localhost:8081/unrecorded"), all);
            assertTrue(all.contains("upstream[seq=1] GET http://other.test/down: was not called"), all);
            assertTrue(all.contains("upstream[seq=2] PUT https://api.vendor.test/v1/x: was not called"), all);
            assertTrue(all.contains("header content-type expected application/json; charset=utf-8 but was [text/plain]"), all);
            assertTrue(all.contains("header authorization expected Bearer {{JWT}} but was Basic x"), all);
            assertTrue(all.contains("header x-kairon expected [k1] but was []"), all);
            assertTrue(all.contains("body $.id"), all);
        }
    }

    @Test
    void sameRequestTwiceConsumesRecordedCallsInSeqOrder() throws Exception {
        String twice = """
                {"schema_version": 1, "node_id": "n", "normalized": false,
                 "mongo": {"available": false, "databases": [], "seed": {}, "written": {}}, "exchanges": [],
                 "upstream": [
                   {"seq": 1, "client": "requests", "request": {"method": "GET", "url": "http://h.test/p", "headers": [],
                      "body": {"encoding": "empty", "value": null}},
                    "response": {"status": 500, "headers": [], "body": {"encoding": "text", "value": "second"}}, "error": null},
                   {"seq": 0, "client": "requests", "request": {"method": "GET", "url": "http://h.test/p", "headers": [],
                      "body": {"encoding": "empty", "value": null}},
                    "response": {"status": 200, "headers": [], "body": {"encoding": "text", "value": "first"}}, "error": null}]}
                """;
        try (UpstreamStubs stubs = UpstreamStubs.start(FixtureLoader.parse("twice", twice))) {
            String base = stubs.toStub("http://h.test");
            assertEquals("first", call("GET", base + "/p", null, null).body());
            HttpResponse<String> second = call("GET", base + "/p", null, null);
            assertEquals(500, second.statusCode());
            assertEquals("second", second.body());
            assertEquals(599, call("GET", base + "/p", null, null).statusCode());
        }
    }
}
