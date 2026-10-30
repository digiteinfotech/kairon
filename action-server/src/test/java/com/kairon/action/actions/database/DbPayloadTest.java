package com.kairon.action.actions.database;

import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.TrackerState;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

/** T-106: ActionUtility.get_payload parity (prompt-db R6 c3-c5). */
class DbPayloadTest {

    private static TrackerState tracker(String text, Map<String, Object> slots, List<Map<String, Object>> entities) {
        Map<String, Object> latest = new LinkedHashMap<>();
        latest.put("text", text);
        latest.put("entities", entities);
        Map<String, Object> tracker = new LinkedHashMap<>();
        tracker.put("sender_id", "u1");
        tracker.put("slots", slots);
        tracker.put("latest_message", latest);
        tracker.put("events", List.of());
        return TrackerState.from(tracker);
    }

    private static TrackerState tracker(String text) {
        return tracker(text, Map.of(), List.of());
    }

    private static Map<String, Object> item(String type, Object value, String queryType) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("type", type);
        item.put("value", value);
        item.put("query_type", queryType);
        return item;
    }

    // ---- c3: value sources ----

    @Test
    void fromSlotUsesSlotValue() {
        TrackerState tracker = tracker("hi", Map.of("topic", "kanban"), List.of());
        assertEquals(Map.of("embedding_search", "kanban"),
                DbPayload.build(List.of(item("from_slot", "topic", "embedding_search")), tracker));
    }

    @Test
    void fromUserMessageUsesLatestText() {
        assertEquals(Map.of("embedding_search", "what is wip"),
                DbPayload.build(List.of(item("from_user_message", "ignored", "embedding_search")), tracker("what is wip")));
    }

    @Test
    void fromUserMessageSlashTextReplacedByKaironUserMsgEntity() {
        TrackerState tracker = tracker("/greet", Map.of(),
                List.of(Map.of("entity", "kairon_user_msg", "value", "hello there")));
        assertEquals(Map.of("embedding_search", "hello there"),
                DbPayload.build(List.of(item("from_user_message", null, "embedding_search")), tracker));
    }

    @Test
    void fromUserMessageSlashTextWithoutEntityKeepsText() {
        assertEquals(Map.of("embedding_search", "/greet"),
                DbPayload.build(List.of(item("from_user_message", null, "embedding_search")), tracker("/greet")));
    }

    @Test
    void otherTypesUseValue() {
        assertEquals(Map.of("embedding_search", "literal"),
                DbPayload.build(List.of(item("from_value", "literal", "embedding_search")), tracker("x")));
    }

    // ---- c4: payload_search ----

    @Test
    void payloadSearchStringParsedAsJson() {
        Map<String, Object> parsed = DbPayload.build(
                List.of(item("from_value", "{\"filter\": {\"must\": [1, 2]}}", "payload_search")), tracker("x"));
        assertEquals(Map.of("payload_search", Map.of("filter", Map.of("must", List.of(1, 2)))), parsed);
    }

    @Test
    void payloadSearchAcceptsAnyJsonValueLikeJsonLoads() {
        assertEquals(Map.of("payload_search", 5),
                DbPayload.build(List.of(item("from_value", "5", "payload_search")), tracker("x")));
        assertEquals(Map.of("payload_search", "a"),
                DbPayload.build(List.of(item("from_value", "\"a\"", "payload_search")), tracker("x")));
    }

    @Test
    void payloadSearchNonStringUsedAsIs() {
        Map<String, Object> filter = Map.of("must", List.of());
        assertEquals(Map.of("payload_search", filter),
                DbPayload.build(List.of(item("from_value", filter, "payload_search")), tracker("x")));
    }

    @Test
    void payloadSearchInvalidJsonFails() {
        ActionFailure failure = assertThrows(ActionFailure.class,
                () -> DbPayload.build(List.of(item("from_value", "{not json", "payload_search")), tracker("x")));
        assertEquals("Error converting payload to JSON: {not json", failure.getMessage());
    }

    @Test
    void payloadSearchTrailingDataFailsLikeJsonLoads() {
        ActionFailure failure = assertThrows(ActionFailure.class,
                () -> DbPayload.build(List.of(item("from_value", "{\"a\": 1} extra", "payload_search")), tracker("x")));
        assertEquals("Error converting payload to JSON: {\"a\": 1} extra", failure.getMessage());
    }

    @Test
    void payloadSearchFromSlotInvalidJsonFails() {
        TrackerState tracker = tracker("x", Map.of("q", "oops"), List.of());
        ActionFailure failure = assertThrows(ActionFailure.class,
                () -> DbPayload.build(List.of(item("from_slot", "q", "payload_search")), tracker));
        assertEquals("Error converting payload to JSON: oops", failure.getMessage());
    }

    // ---- c5: embedding_search concatenation ----

    @Test
    void otherQueryTypesJoinedBySingleSpace() {
        TrackerState tracker = tracker("user words", Map.of("s", "slot words"), List.of());
        List<Map<String, Object>> spec = List.of(
                item("from_value", "first", "embedding_search"),
                item("from_slot", "s", "embedding_search"),
                item("from_user_message", null, "something_else"),
                item("from_value", 7, "embedding_search"));
        assertEquals(Map.of("embedding_search", "first slot words user words 7"), DbPayload.build(spec, tracker));
    }

    @Test
    void mixedQueryTypesKeepBothKeys() {
        Map<String, Object> built = DbPayload.build(List.of(
                item("from_value", "kanban", "embedding_search"),
                item("from_value", "{\"x\": true}", "payload_search")), tracker("x"));
        assertEquals(List.of("embedding_search", "payload_search"), new ArrayList<>(built.keySet()));
        assertEquals("kanban", built.get("embedding_search"));
        assertEquals(Map.of("x", true), built.get("payload_search"));
    }

    @Test
    void singleNonStringValueKeptAsIs() {
        assertEquals(Map.of("embedding_search", 3),
                DbPayload.build(List.of(item("from_value", 3, "embedding_search")), tracker("x")));
    }

    @Test
    void appendedValuesUsePythonStr() {
        Map<String, Object> built = DbPayload.build(List.of(
                item("from_value", "a", "embedding_search"),
                item("from_value", null, "embedding_search"),
                item("from_value", true, "embedding_search")), tracker("x"));
        assertEquals("a None True", built.get("embedding_search"));
    }

    @Test
    void appendingToNonStringFailsLikePythonTypeError() {
        Map<String, Object> slots = new HashMap<>();
        slots.put("missing", null);
        TrackerState tracker = tracker("x", slots, List.of());
        ActionFailure failure = assertThrows(ActionFailure.class, () -> DbPayload.build(List.of(
                item("from_slot", "missing", "embedding_search"),
                item("from_value", "b", "embedding_search")), tracker));
        assertEquals("unsupported operand type(s) for +=: 'NoneType' and 'str'", failure.getMessage());
    }

    @Test
    void emptySpecGivesEmptyPayload() {
        assertEquals(Map.of(), DbPayload.build(List.of(), tracker("x")));
        assertEquals(Map.of(), DbPayload.build(null, tracker("x")));
    }
}
