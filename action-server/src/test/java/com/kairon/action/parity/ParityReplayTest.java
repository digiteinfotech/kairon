package com.kairon.action.parity;

import com.kairon.action.ActionSettings;
import com.kairon.action.catalog.MemoryActionCatalog;
import io.micronaut.runtime.server.EmbeddedServer;
import io.micronaut.test.extensions.junit5.annotation.MicronautTest;
import jakarta.inject.Inject;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestFactory;
import org.junit.jupiter.api.io.TempDir;
import org.opentest4j.AssertionFailedError;
import org.opentest4j.TestAbortedException;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

/**
 * Parity replay (parity-harness R3): one dynamic test per fixture, named by its node id. Each test seeds the
 * catalog, serves the recorded upstream replies, POSTs the recorded request and compares the response, the
 * outbound calls (none missing, none extra) and the written documents ({@link FixtureReplay#run}). A failing
 * fixture reports all of its mismatches as the test's failure message.
 * <p>
 * Fixtures come from {@link FixtureSources}: the bundled synthetic ones plus, when {@code kairon.parity.fixtures} /
 * {@code KAIRON_PARITY_FIXTURES} is set, the Python recorder's output.
 */
@MicronautTest
class ParityReplayTest {

    static final String NO_EXCHANGE = "no inbound /webhook exchange recorded: the node calls actions directly"
            + " and cannot be replayed through the server (parity-harness R5)";

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

    @TestFactory
    Stream<DynamicTest> replayFixtures() {
        return FixtureSources.files(FixtureSources.directories()).stream().map(this::replayTest);
    }

    /** The dynamic test for one fixture file; an unreadable file becomes a failing test named by its file name. */
    DynamicTest replayTest(Path file) {
        Fixture fixture;
        try {
            fixture = FixtureLoader.load(file);
        } catch (RuntimeException e) {
            String message = file + ": " + e.getMessage();
            return DynamicTest.dynamicTest(file.getFileName() + " (unreadable fixture)", file.toUri(), () -> fail(message, e));
        }
        return DynamicTest.dynamicTest(fixture.nodeId(), file.toUri(), () -> {
            Assumptions.assumeFalse(fixture.exchanges().isEmpty(), NO_EXCHANGE);
            FixtureReplay.Result result = FixtureReplay.run(fixture, server.getPort(), catalog, settings);
            if (!result.passed()) {
                fail(result.report());
            }
        });
    }

    // ------------------------------------------------------------------ the factory itself

    private static Path copy(Path dir, String bundled, String from, String to) throws IOException {
        Path source = FixtureSources.bundled().resolve(bundled);
        String json = Files.readString(source);
        assertTrue(json.contains(from), "fixture has no " + from);
        Path target = dir.resolve(bundled);
        Files.writeString(target, json.replace(from, to));
        return target;
    }

    @Test
    void factoryNamesEachBundledFixtureByNodeIdAndRunsItClean() throws Throwable {
        List<Path> files = FixtureSources.files(List.of(FixtureSources.bundled()));
        assertEquals(3, files.size(), files.toString());
        List<DynamicTest> tests = files.stream().map(this::replayTest).toList();
        assertEquals(List.of(
                "synthetic/parity_replay_test.py::test_http_action_https_get_query",
                "synthetic/parity_replay_test.py::test_http_action_post_with_auth_header",
                "synthetic/parity_replay_test.py::test_slot_set_action_from_value"),
                tests.stream().map(DynamicTest::getDisplayName).sorted().toList());
        for (DynamicTest test : tests) {
            assertTrue(test.getTestSourceUri().isPresent());
            test.getExecutable().execute();
        }
    }

    @Test
    void mismatchesBecomeTheFailureMessage(@TempDir Path dir) throws IOException {
        Path file = copy(dir, "synthetic_http_action_post-0000000002.json",
                "[\"Authorization\", \"Bearer order-token\"]", "[\"Authorization\", \"Bearer other\"]");
        DynamicTest test = replayTest(file);
        assertEquals("synthetic/parity_replay_test.py::test_http_action_post_with_auth_header", test.getDisplayName());
        AssertionFailedError error = assertThrows(AssertionFailedError.class, () -> test.getExecutable().execute());
        assertTrue(error.getMessage().startsWith("synthetic/parity_replay_test.py::test_http_action_post_with_auth_header:"),
                error.getMessage());
        assertTrue(error.getMessage().contains("header authorization expected Bearer other but was Bearer order-token"),
                error.getMessage());
    }

    @Test
    void unreadableFixtureFailsUnderItsFileName(@TempDir Path dir) throws IOException {
        Path file = dir.resolve("broken.json");
        Files.writeString(file, "{\"schema_version\": 99}");
        DynamicTest test = replayTest(file);
        assertEquals("broken.json (unreadable fixture)", test.getDisplayName());
        assertThrows(AssertionFailedError.class, () -> test.getExecutable().execute());
    }

    @Test
    void fixtureWithoutExchangeIsSkippedNotPassed(@TempDir Path dir) throws IOException {
        Path source = FixtureSources.bundled().resolve("synthetic_slot_set_action-0000000001.json");
        Fixture original = FixtureLoader.load(source);
        String json = Files.readString(source);
        int start = json.indexOf("\"exchanges\": [");
        int end = json.indexOf("\"upstream\":");
        Path file = dir.resolve("no_exchange.json");
        Files.writeString(file, json.substring(0, start) + "\"exchanges\": [],\n  " + json.substring(end));
        DynamicTest test = replayTest(file);
        assertEquals(original.nodeId(), test.getDisplayName());
        TestAbortedException aborted = assertThrows(TestAbortedException.class, () -> test.getExecutable().execute());
        assertTrue(aborted.getMessage().contains("parity-harness R5"), aborted.getMessage());
    }
}
