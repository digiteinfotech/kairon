package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.TrackerState;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

/** templating-and-secrets R3 c3 (latest_message falls through like Python) and R4 c1-c2 (evaluation context). */
class ContextAndParameterTest {

    private static final String BOT = "ctx-bot";
    private static final List<String> BUILD_CONTEXT_KEYS = List.of("sender_id", "user_message", "slot", "intent",
            "chat_log", "key_vault", "latest_message", "kairon_user_msg", "session_started");

    private ActionSupport support;
    private TrackerState tracker;
    private Map<String, Object> latest;

    @BeforeEach
    void setUp() {
        ActionSettings settings = new ActionSettings();
        MemoryActionCatalog catalog = new MemoryActionCatalog();
        catalog.put("key_vault", new Document("bot", BOT).append("key", "TOKEN").append("value", "abc"));
        catalog.put("key_vault", new Document("bot", BOT).append("key", "OTHER").append("value", "xyz"));
        support = new ActionSupport(catalog, settings, new Tokens(settings), new HttpCaller(settings));
        latest = new LinkedHashMap<>();
        latest.put("text", "/greet");
        latest.put("intent", Map.of("name", "greet", "confidence", 1.0));
        latest.put("intent_ranking", List.of(Map.of("name", "greet", "confidence", 1.0)));
        latest.put("entities", List.of(Map.of("entity", "kairon_user_msg", "value", "hello there")));
        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("sender_id", "user-1");
        raw.put("slots", Map.of("bot", BOT, "city", "Pune"));
        raw.put("latest_message", latest);
        raw.put("events", List.of(Map.of("event", "session_started", "timestamp", 1700000000.5),
                Map.of("event", "user", "text", "/greet")));
        tracker = TrackerState.from(raw);
    }

    @Test
    void contextHasPythonKeysAndKeyVaultOnlyWhenRequested() {
        Map<String, Object> without = support.context(tracker, false);
        assertEquals(BUILD_CONTEXT_KEYS, List.copyOf(without.keySet()));
        assertEquals(Map.of(), without.get("key_vault"));
        assertEquals("user-1", without.get("sender_id"));
        assertEquals("/greet", without.get("user_message"));
        assertEquals("greet", without.get("intent"));
        assertEquals(latest, without.get("latest_message"));
        assertEquals("hello there", without.get("kairon_user_msg"));
        assertEquals("2023-11-14 22:13:20", without.get("session_started"));
        assertFalse(without.containsKey("bot"));

        Map<String, Object> with = support.context(tracker, true);
        assertEquals(BUILD_CONTEXT_KEYS, List.copyOf(with.keySet()));
        assertEquals("{\"TOKEN\": \"abc\", \"OTHER\": \"xyz\"}", Jsons.pythonDumps(with.get("key_vault")));
    }

    @Test
    void contextWithBotAppendsBotLast() {
        Map<String, Object> context = support.context(tracker, true, BOT);
        List<String> keys = new java.util.ArrayList<>(BUILD_CONTEXT_KEYS);
        keys.add("bot");
        assertEquals(keys, List.copyOf(context.keySet()));
        assertEquals(BOT, context.get("bot"));
        assertEquals(Map.of("TOKEN", "abc", "OTHER", "xyz"), context.get("key_vault"));

        Map<String, Object> noVault = support.context(tracker, false, BOT);
        assertEquals(Map.of(), noVault.get("key_vault"));
        assertEquals(BOT, noVault.get("bot"));
    }

    /** Python get_parameter_value has no latest_message branch: it falls through to param['value']. */
    @Test
    void latestMessageParameterFallsThroughToConfiguredValue() {
        Map<String, Object> context = support.context(tracker, false);
        Map<String, Object> param = new LinkedHashMap<>();
        param.put("key", "msg");
        param.put("parameter_type", "latest_message");
        param.put("value", "literal");
        assertEquals("literal", support.parameter(context, param, BOT));

        ActionSupport.Prepared prepared = support.prepareRequest(context, List.of(param), BOT);
        assertEquals("literal", prepared.body().get("msg"));
        assertEquals("literal", prepared.log().get("msg"));
    }

    @Test
    void otherTrackerParameterTypesStillResolve() {
        Map<String, Object> context = support.context(tracker, false);
        assertEquals("user-1", support.parameter(context, Map.of("parameter_type", "sender_id"), BOT));
        assertEquals("hello there", support.parameter(context, Map.of("parameter_type", "user_message"), BOT));
        assertEquals("greet", support.parameter(context, Map.of("parameter_type", "intent"), BOT));
        assertEquals("Pune", support.parameter(context, Map.of("parameter_type", "slot", "value", "city"), BOT));
    }

    @Test
    void missingParameterTypeIsQuotedKeyError() {
        Map<String, Object> context = support.context(tracker, false);
        ActionFailure failure = assertThrows(ActionFailure.class,
                () -> support.parameter(context, Map.of("key", "city", "value", "Pune"), BOT));
        assertEquals("'parameter_type'", failure.getMessage());
    }

    @Test
    void prepareRequestMissingKeyIsQuotedKeyError() {
        Map<String, Object> context = support.context(tracker, false);
        ActionFailure failure = assertThrows(ActionFailure.class,
                () -> support.prepareRequest(context, List.of(Map.of("parameter_type", "value", "value", "x")), BOT));
        assertEquals("'key'", failure.getMessage());
    }

    @Test
    void oneWithoutKeyResolvesValueLikeGetParameterValue() {
        Map<String, Object> context = support.context(tracker, false);
        assertEquals("2030-01-15 10:30:00",
                support.one(context, Map.of("parameter_type", "value", "value", "2030-01-15 10:30:00"), BOT));
    }
}
