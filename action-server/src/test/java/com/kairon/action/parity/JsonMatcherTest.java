package com.kairon.action.parity;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class JsonMatcherTest {

    private static JsonNode json(String text) {
        try {
            return FixtureLoader.JSON.readTree(text);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    private static JsonMatcher matcher() {
        return new JsonMatcher(new Placeholders.Bindings());
    }

    @Test
    void plainValuesCompareStructurally() {
        JsonMatcher m = matcher();
        assertTrue(m.matches(json("{\"a\": 1, \"b\": [1, \"x\", null]}"), json("{\"b\": [1, \"x\", null], \"a\": 1.0}")));
        assertTrue(m.matches(json("{\"n\": {\"$numberInt\": \"5\"}}"), json("{\"n\": {\"$numberLong\": \"5\"}}")));
        List<String> problems = m.compare(json("{\"a\": [1, 2], \"b\": \"x\"}"), json("{\"a\": [2, 1], \"c\": true}"));
        assertTrue(problems.contains("$.a[0]: expected 1 but was 2"), problems.toString());
        assertTrue(problems.contains("$.b: missing, expected \"x\""), problems.toString());
        assertTrue(problems.contains("$.c: unexpected field with value true"), problems.toString());
        assertFalse(m.matches(json("[1, 2]"), json("[1, 2, 3]")));
    }

    @Test
    void wholeValueTokensMatchTheirShapeOnly() {
        JsonMatcher m = matcher();
        assertTrue(m.matches(json("\"{{TIMESTAMP}}\""), json("{\"$date\": {\"$numberLong\": \"1\"}}")));
        assertTrue(m.matches(json("\"{{DATETIME}}\""), json("\"2024-01-01T10:00:00.123456\"")));
        assertFalse(m.matches(json("\"{{DATETIME}}\""), json("\"yesterday\"")));
        assertTrue(m.matches(json("\"{{EPOCH}}\""), json("1704067200")));
        assertTrue(m.matches(json("\"{{EPOCH}}\""), json("\"1704067200123\"")));
        assertTrue(m.matches(json("\"{{OBJECT_ID:1}}\""), json("{\"$oid\": \"65a1f0c2e4b0a1b2c3d4e5f1\"}")));
        assertFalse(m.matches(json("\"{{OBJECT_ID:9}}\""), json("\"not-an-id\"")));
        assertTrue(m.matches(json("\"{{UUID_HEX:1}}\""), json("\"0f8fad5bd9cb469fa16570867728950e\"")));
        assertFalse(m.matches(json("\"{{UUID_HEX:2}}\""), json("\"0f8fad5b-d9cb-469f-a165-70867728950e\"")));
        assertTrue(m.matches(json("\"{{JWT}}\""), json("\"eyJhbGciOi.eyJzdWIiOi.c2ln\"")));
        assertTrue(m.matches(json("\"{{REQUEST_ID}}\""), json("\"anything\"")));
        assertFalse(m.matches(json("\"{{REQUEST_ID}}\""), json("null")));
    }

    @Test
    void indexedTokensMustBindConsistentlyAcrossTheFixture() {
        JsonMatcher m = matcher();
        String a = "0f8fad5b-d9cb-469f-a165-70867728950e";
        String b = "7c9e6679-7425-40de-944b-e07fc1f90ae7";
        assertTrue(m.matches(json("{\"id\": \"{{UUID:1}}\"}"), json("{\"id\": \"" + a + "\"}")));
        // Same index elsewhere in the fixture (here: inside a URL template) must be the same value.
        assertTrue(m.matchesString("http://h/cb/{{UUID:1}}?x=1", "http://h/cb/" + a + "?x=1"));
        assertFalse(m.matchesString("http://h/cb/{{UUID:1}}?x=1", "http://h/cb/" + b + "?x=1"));
        // A different index may not reuse the value bound to index 1...
        assertFalse(m.matches(json("\"{{UUID:2}}\""), json("\"" + a + "\"")));
        // ...but binds freely to a new value, which then sticks.
        assertTrue(m.matches(json("\"{{UUID:2}}\""), json("\"" + b + "\"")));
        assertFalse(m.matches(json("[\"{{UUID:1}}\", \"{{UUID:2}}\"]"), json("[\"" + b + "\", \"" + a + "\"]")));
        assertEquals(a, m.bindings().get("UUID:1"));
        assertEquals(b, m.bindings().get("UUID:2"));
    }

    @Test
    void failedComparisonLeavesBindingsUntouched() {
        JsonMatcher m = matcher();
        String id = "65a1f0c2e4b0a1b2c3d4e5f1";
        assertFalse(m.matches(json("{\"id\": \"{{OBJECT_ID:1}}\", \"x\": 1}"), json("{\"id\": \"" + id + "\", \"x\": 2}")));
        assertEquals(null, m.bindings().get("OBJECT_ID:1"));
        assertTrue(m.matches(json("\"{{OBJECT_ID:1}}\""), json("\"65a1f0c2e4b0a1b2c3d4e5f2\"")));
    }

    @Test
    void embeddedTokensMatchAsTemplates() {
        JsonMatcher m = matcher();
        assertTrue(m.matchesString("Bearer {{JWT}}", "Bearer aaa.bbb.ccc"));
        assertFalse(m.matchesString("Bearer {{JWT}}", "Basic aaa.bbb.ccc"));
        assertTrue(m.matches(json("\"sent at {{DATETIME}} by {{OBJECT_ID:3}}\""),
                json("\"sent at 2024-01-01 10:00:00 by 65a1f0c2e4b0a1b2c3d4e5f1\"")));
        assertTrue(m.matchesString("/api/events/dispatch/{{UUID_HEX:1}}", "/api/events/dispatch/0f8fad5bd9cb469fa16570867728950e"));
        // Literal regex characters in the template are not special.
        assertFalse(m.matchesString("a.b?{{EPOCH}}", "aXb?123"));
    }

    @Test
    void ignoresTopLevelKeysAndDatesWhenAsked() {
        JsonMatcher m = matcher().ignoringTopLevel(Set.of("_id", "timestamp")).ignoringDates();
        assertTrue(m.matches(
                json("{\"_id\": {\"$oid\": \"65a1f0c2e4b0a1b2c3d4e5f1\"}, \"timestamp\": 1, \"at\": {\"$date\": \"2020-01-01T00:00:00Z\"}, \"v\": 1}"),
                json("{\"_id\": \"other\", \"at\": {\"$date\": {\"$numberLong\": \"5\"}}, \"v\": 1}")));
        // Only top-level keys are ignored.
        assertFalse(m.matches(json("{\"inner\": {\"_id\": 1}}"), json("{\"inner\": {\"_id\": 2}}")));
    }

    @Test
    void volatileDurationsAndReplyDatesAreSkippedWhenAsked() {
        JsonMatcher m = matcher().ignoringVolatile();
        assertTrue(m.matches(
                json("{\"time_elapsed\": 1.5, \"events\": [{\"time_elapsed\": {\"$numberInt\": \"0\"},"
                        + " \"response_headers\": {\"content-type\": \"application/json\"}}]}"),
                json("{\"time_elapsed\": {\"$numberDouble\": \"92.6\"}, \"events\": [{\"time_elapsed\": 7,"
                        + " \"response_headers\": {\"content-type\": \"application/json\", \"date\": \"Mon, 26 Oct 2026 14:29:55 GMT\"}}]}")));
        // Presence of time_elapsed is still asserted, and a non-numeric value is compared normally.
        assertFalse(m.matches(json("{\"time_elapsed\": 1}"), json("{}")));
        assertFalse(m.matches(json("{\"time_elapsed\": 1}"), json("{\"time_elapsed\": \"slow\"}")));
        // A date key outside response_headers is not volatile.
        assertFalse(m.matches(json("{\"headers\": {\"date\": \"a\"}}"), json("{\"headers\": {\"date\": \"b\"}}")));
        // Without the option the rules do not apply.
        assertFalse(matcher().matches(json("{\"time_elapsed\": 1}"), json("{\"time_elapsed\": 2}")));
    }
}
