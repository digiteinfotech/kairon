package com.kairon.action.parity;

import com.kairon.action.ActionSettings;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReplayEndpointsTest {

    private static final String FIXTURE = """
            {"schema_version": 1, "node_id": "n", "normalized": true,
             "mongo": {"available": false, "databases": [], "seed": {}, "written": {}},
             "exchanges": [],
             "upstream": [
               {"seq": 0, "client": "requests", "request": {"method": "POST", "url": "http://localhost:8080/evaluate",
                  "headers": [], "body": {"encoding": "json", "value": {}}},
                "response": {"status": 200, "headers": [], "body": {"encoding": "json", "value": {}}}, "error": null}
             ]}
            """;

    @Test
    void recordedOriginsMapToStubsOthersToTheReportingStub() {
        try (UpstreamStubs stubs = UpstreamStubs.start(FixtureLoader.parse("n", FIXTURE))) {
            String stub = stubs.httpOrigins().get("http://localhost:8080");
            assertEquals(stub + "/evaluate", ReplayEndpoints.target("http://localhost:8080/evaluate", stubs));
            assertEquals(stub + "/format", ReplayEndpoints.target("http://localhost:8080/format", stubs));
            assertEquals("https://llm.test/v1", ReplayEndpoints.target("https://llm.test/v1", stubs));
            assertEquals(stubs.httpsBase(), ReplayEndpoints.target("http://localhost:5001", stubs));
            assertEquals(stubs.httpsBase() + "/api/v1", ReplayEndpoints.target("http://localhost:8000/api/v1", stubs));
            assertEquals("", ReplayEndpoints.target("", stubs));
        }
    }

    @Test
    void applySetsEverySettingAndRestoreUndoesIt() {
        ActionSettings settings = new ActionSettings();
        settings.setPyscriptUrl("http://before/pyscript");
        settings.setWebSearchUrl("http://before/websearch");
        try (UpstreamStubs stubs = UpstreamStubs.start(FixtureLoader.parse("n", FIXTURE))) {
            ReplayEndpoints.Saved saved = ReplayEndpoints.apply(settings, stubs);
            String stub = stubs.httpOrigins().get("http://localhost:8080");
            assertEquals(stub + "/evaluate", settings.getPyscriptUrl());
            assertEquals(stub + "/format", settings.getEvaluatorUrl());
            assertTrue(settings.getEventsServerUrl().startsWith(stubs.httpsBase()), settings.getEventsServerUrl());
            assertEquals("", settings.getWebSearchUrl(), "unset in the Python configuration");
            saved.restore();
        }
        assertEquals("http://before/pyscript", settings.getPyscriptUrl());
        assertEquals("http://before/websearch", settings.getWebSearchUrl());
    }

    @Test
    void systemPropertyOverridesThePythonDefault() {
        String key = ReplayEndpoints.OVERRIDE_PREFIX + "web-search";
        System.setProperty(key, "https://search.test/run");
        try {
            ReplayEndpoints.Endpoint webSearch = ReplayEndpoints.ENDPOINTS.stream()
                    .filter(e -> e.name().equals("web-search")).findFirst().orElseThrow();
            assertEquals("https://search.test/run", webSearch.recorded());
        } finally {
            System.clearProperty(key);
        }
    }
}
