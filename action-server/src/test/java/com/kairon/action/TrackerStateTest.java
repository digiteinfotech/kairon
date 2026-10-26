package com.kairon.action;

import com.kairon.action.runtime.RequestIds;
import com.kairon.action.runtime.TrackerState;
import org.junit.jupiter.api.Test;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

/** rasa_sdk Tracker.from_dict defaults (webhook-contract R1) and request id resolution (R4). */
class TrackerStateTest {

    @Test
    void defaultsMatchRasaSdk() {
        TrackerState tracker = TrackerState.from(Map.of("sender_id", "s1"));
        assertEquals("s1", tracker.senderId);
        assertEquals(Map.of(), tracker.slots);
        assertEquals(Map.of(), tracker.latestMessage);
        assertEquals(List.of(), tracker.events);
        assertEquals(false, tracker.paused);
        assertNull(tracker.followupAction);
        assertEquals(Map.of(), tracker.activeLoop);
        assertNull(tracker.latestActionName);
        assertEquals(List.of(), tracker.stack);
    }

    @Test
    void activeFormIsTheFallbackActiveLoop() {
        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("sender_id", "s1");
        raw.put("active_form", Map.of("name", "booking_form"));
        assertEquals(Map.of("name", "booking_form"), TrackerState.from(raw).activeLoop);
        raw.put("active_loop", Map.of("name", "loop"));
        assertEquals(Map.of("name", "loop"), TrackerState.from(raw).activeLoop);
    }

    @Test
    void presentValuesAreKept() {
        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("sender_id", "s1");
        raw.put("paused", true);
        raw.put("latest_action_name", "action_listen");
        raw.put("stack", List.of("frame"));
        raw.put("followup_action", "utter_x");
        TrackerState tracker = TrackerState.from(raw);
        assertEquals(true, tracker.paused);
        assertEquals("action_listen", tracker.latestActionName);
        assertEquals(List.of("frame"), tracker.stack);
        assertEquals("utter_x", tracker.followupAction);
    }

    @Test
    void senderIdDecryptsWhenPossibleElseUnchanged() {
        Map<String, Object> raw = Map.of("sender_id", "token");
        assertEquals("user@x.com", TrackerState.from(raw, id -> "user@x.com").senderId);
        assertEquals("token", TrackerState.from(raw, id -> {
            throw new IllegalArgumentException("not fernet");
        }).senderId);
    }

    @Test
    void requestIdResolution() {
        assertEquals("abc", RequestIds.resolve("  abc "));
        for (String absent : new String[]{null, "", "   "}) {
            UUID uuid = UUID.fromString(RequestIds.resolve(absent));
            assertEquals(4, uuid.version());
        }
    }
}
