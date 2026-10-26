package com.kairon.action.parity;

import com.kairon.action.ActionSettings;
import com.kairon.action.catalog.MemoryActionCatalog;
import io.micronaut.runtime.server.EmbeddedServer;
import io.micronaut.test.extensions.junit5.annotation.MicronautTest;
import jakarta.inject.Inject;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** End-to-end replay of the synthetic fixtures through the embedded server and in-memory catalog. */
@MicronautTest
class FixtureReplayTest {

    static final String DIR = "/parity/fixtures/";
    static final String SLOT_SET = DIR + "synthetic_slot_set_action-0000000001.json";
    static final String HTTP_POST = DIR + "synthetic_http_action_post-0000000002.json";
    static final String HTTPS_GET = DIR + "synthetic_http_action_https_get-0000000003.json";

    @Inject
    EmbeddedServer server;

    @Inject
    MemoryActionCatalog catalog;

    @Inject
    ActionSettings settings;

    @AfterEach
    void clean() {
        catalog.clear();
    }

    private FixtureReplay.Result replay(Fixture fixture) {
        return FixtureReplay.run(fixture, server.getPort(), catalog, settings);
    }

    private static String text(String resource) {
        try (InputStream in = FixtureReplayTest.class.getResourceAsStream(resource)) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
    }

    private static Fixture variant(String resource, String from, String to) {
        String json = text(resource);
        assertTrue(json.contains(from), "fixture has no " + from);
        return FixtureLoader.parse(resource + " (variant)", json.replace(from, to));
    }

    @Test
    void slotSetFixtureReplaysClean() {
        FixtureReplay.Result result = replay(FixtureLoader.loadResource(SLOT_SET));
        assertTrue(result.passed(), result.report());
        assertTrue(result.hits().isEmpty());
    }

    @Test
    void httpPostFixtureReplaysCleanThroughPerOriginStub() {
        FixtureReplay.Result result = replay(FixtureLoader.loadResource(HTTP_POST));
        assertTrue(result.passed(), result.report());
        assertEquals(1, result.hits().size());
        UpstreamStubs.Hit hit = result.hits().get(0);
        assertEquals("http://localhost:8081", hit.stub());
        assertEquals("POST", hit.method());
        assertEquals("/orders", hit.path());
        assertEquals("Bearer order-token", hit.header("Authorization"));
    }

    @Test
    void httpsFixtureReplaysCleanThroughSharedHttpsStub() {
        String before = settings.getHttpsStubBase();
        FixtureReplay.Result result = replay(FixtureLoader.loadResource(HTTPS_GET));
        assertTrue(result.passed(), result.report());
        assertEquals(1, result.hits().size());
        assertEquals("city=Pune", result.hits().get(0).query());
        assertEquals(before, settings.getHttpsStubBase(), "https stub base is restored");
    }

    @Test
    void responseDifferenceIsReported() {
        Fixture fixture = variant(SLOT_SET, "\"name\": \"location\", \"value\": \"Bengaluru\"}", "\"name\": \"location\", \"value\": \"Mumbai\"}");
        FixtureReplay.Result result = replay(fixture);
        assertFalse(result.passed());
        assertTrue(result.mismatches().stream().anyMatch(m -> m.startsWith("exchanges[0]: body $.events[0].value")),
                result.report());
    }

    @Test
    void inconsistentPlaceholderIndexIsReported() {
        // The upstream reply's order id fills both the response and the log; claiming the log holds a different
        // uuid index than the response must fail even though each value alone is a valid UUID.
        Fixture fixture = variant(HTTP_POST, "\"bot_response\": \"Order {{UUID:1}} placed\"", "\"bot_response\": \"Order {{UUID:2}} placed\"");
        FixtureReplay.Result result = replay(fixture);
        assertFalse(result.passed());
        assertTrue(result.mismatches().stream().anyMatch(m -> m.contains("written action_server_logs.inserted")
                && m.contains("bot_response")), result.report());
    }

    @Test
    void outboundBodyAndHeaderDifferencesAreReported() {
        Fixture fixture = FixtureLoader.parse("variant", text(HTTP_POST)
                .replace("[\"Authorization\", \"Bearer order-token\"]", "[\"Authorization\", \"Bearer other\"]")
                .replace("{\"item\": \"pizza\", \"quantity\": \"2\"}", "{\"item\": \"pasta\", \"quantity\": \"2\"}"));
        List<String> mismatches = replay(fixture).mismatches();
        assertTrue(mismatches.stream().anyMatch(m -> m.contains("header authorization")), String.join("\n", mismatches));
        assertTrue(mismatches.stream().anyMatch(m -> m.contains("body $.item")), String.join("\n", mismatches));
    }

    @Test
    void missingAndExtraOutboundCallsAreReported() {
        // Recorded URL differs from what the config calls: the recorded call is never made and the real one is extra.
        Fixture fixture = FixtureLoader.parse("variant", text(HTTP_POST)
                .replace("\"url\": \"http://localhost:8081/orders\",\n        \"headers\"",
                        "\"url\": \"http://localhost:8081/orders/v2\",\n        \"headers\""));
        List<String> mismatches = replay(fixture).mismatches();
        assertTrue(mismatches.stream().anyMatch(m -> m.contains("/orders/v2: was not called")), String.join("\n", mismatches));
        assertTrue(mismatches.stream().anyMatch(m -> m.startsWith("unexpected upstream call POST http://localhost:8081/orders")),
                String.join("\n", mismatches));
    }

    @Test
    void unrecordedWriteIsReported() {
        Fixture fixture = variant(SLOT_SET, "\"messages\": [\"Setting slot 'location' to 'Bengaluru'.\", \"Resetting slot 'age' value to None.\"]",
                "\"messages\": [\"Setting slot 'location' to 'Bengaluru'.\"]");
        List<String> mismatches = replay(fixture).mismatches();
        assertTrue(mismatches.stream().anyMatch(m -> m.startsWith("written action_server_logs.inserted: $.messages")),
                String.join("\n", mismatches));
    }
}
