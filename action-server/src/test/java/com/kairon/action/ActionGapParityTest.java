package com.kairon.action;

import com.kairon.action.actions.ActionFactory;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.HttpCaller;
import com.kairon.action.support.Tokens;
import io.micronaut.runtime.server.EmbeddedServer;
import io.micronaut.test.extensions.junit5.annotation.MicronautTest;
import jakarta.inject.Inject;
import org.bson.Document;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Packet T-028..T-031: deferred types and no rephrase (dispatch-and-logging R1 c6, core-actions R4 c4),
 * two-stage text search (core-actions R3 c2), google CSE request (integration-actions R3 c3),
 * voice provider initiate-call (integration-actions R12 c2).
 */
@MicronautTest
class ActionGapParityTest {

    @Inject
    EmbeddedServer server;
    @Inject
    MemoryActionCatalog catalog;
    @Inject
    Tokens tokens;
    @Inject
    ActionSupport support;
    @Inject
    ActionFactory factory;
    @Inject
    HttpCaller http;
    @Inject
    ActionSettings settings;

    ParityKit kit;

    @BeforeAll
    static void servers() throws Exception {
        ParityKit.startServers();
    }

    @AfterAll
    static void stop() {
        ParityKit.stopServers();
    }

    @BeforeEach
    void reset() {
        kit = new ParityKit(server, catalog, tokens, support, factory, http, settings);
        kit.restore();
        kit.resetState();
    }

    // ---- T-028: deferred types ----

    @Test
    void deferredTypesAreUnsupported() {
        for (String type : List.of("prompt_action", "database_action")) {
            String name = "act_" + type;
            kit.register(name, type);
            ActionFailure failure = kit.failureOf(() -> factory.get(kit.bot, name));
            assertEquals(type + " type action is not supported with action server", failure.getMessage());

            Map<String, Object> body = kit.ok(name);
            assertEquals(List.of(), body.get("events"));
            assertEquals(List.of(), body.get("responses"));
            Document log = kit.log(name);
            assertNull(log.get("type"));
            assertEquals(type + " type action is not supported with action server", log.get("exception"));
            assertEquals(Kairon.FAIL, log.get("status"));
        }
    }

    // ---- T-028: kairon_bot_response never rephrases ----

    @Test
    void botResponseIgnoresRephraseFlag() {
        kit.put("bot_settings", kit.doc("bot", kit.bot, "status", true, "rephrase_response", true));
        Map<String, Object> domain = Map.of("responses", Map.of("utter_greet", List.of(Map.of("text", "Hello"))));
        Map<String, Object> body = kit.ok("utter_greet", kit.slots(), kit.latest("hi"), List.of(), domain, "default", "utter_greet", null, null);
        assertEquals("utter_greet", kit.responses(body).get(0).get("response"));
        assertEquals(Map.of("response", "utter_greet"), kit.event(body, Kairon.ACTION_RESPONSE).get("value"));
        assertTrue(ParityKit.HITS.stream().noneMatch(hit -> hit.path().contains("/llm")), "no LLM call");
        Document log = kit.log("utter_greet");
        assertEquals("kairon_bot_response", log.get("type"));
        assertEquals(Kairon.SUCCESS, log.get("status"));
        assertEquals(true, log.get("enable_rephrasing"));
        assertEquals(false, log.get("is_rephrased"));
        assertTrue(log.containsKey("raw_gpt_response"));
        assertNull(log.get("raw_gpt_response"));
    }

    @Test
    void botResponseRephraseDisabledDefaults() {
        Map<String, Object> domain = Map.of("responses", Map.of("utter_bye", List.of(Map.of("text", "Bye"))));
        kit.ok("utter_bye", kit.slots(), kit.latest("bye"), List.of(), domain, "default", "utter_bye", null, null);
        Document log = kit.log("utter_bye");
        assertEquals(false, log.get("enable_rephrasing"));
        assertEquals(false, log.get("is_rephrased"));
        assertNull(log.get("raw_gpt_response"));
    }

    @Test
    void botResponseWithoutTemplatesFailsButStillUtters() {
        Map<String, Object> body = kit.ok("utter_missing", kit.slots(), kit.latest("hi"), List.of(),
                Map.of("responses", Map.of()), "default", "utter_missing", null, null);
        assertEquals("utter_missing", kit.responses(body).get(0).get("response"));
        Document log = kit.log("utter_missing");
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals("Cannot choose from an empty sequence", log.get("exception"));
    }

    // ---- T-029: two-stage text search ----

    private void fallback(int count) {
        kit.register("fallback", "two_stage_fallback");
        kit.put("kairon_two_stage_fallback_action", kit.doc(
                "bot", kit.bot, "name", "fallback", "status", true, "fallback_message", "Try these",
                "text_recommendations", new Document("count", count).append("use_intent_ranking", false)));
        kit.put("training_examples", kit.doc("bot", kit.bot, "text", "flight status please", "status", true, "intent", "status"));
        kit.put("training_examples", kit.doc("bot", kit.bot, "text", "book a flight", "status", true, "intent", "book"));
        kit.put("training_examples", kit.doc("bot", kit.bot, "text", "hotel booking", "status", true, "intent", "hotel"));
        kit.put("training_examples", kit.doc("bot", kit.bot, "text", "cancel flight", "status", false, "intent", "cancel"));
        kit.put("training_examples", kit.doc("bot", "other-bot", "text", "flight", "status", true, "intent", "x"));
    }

    @SuppressWarnings("unchecked")
    private List<String> buttonTexts(Map<String, Object> body) {
        List<Map<String, Object>> buttons = (List<Map<String, Object>>) kit.responses(body).get(0).get("buttons");
        return buttons.stream().map(button -> {
            assertEquals(button.get("text"), button.get("payload"));
            return String.valueOf(button.get("text"));
        }).toList();
    }

    @Test
    void twoStageTextSearchOrderedByScoreAndLimited() {
        fallback(1);
        Map<String, Object> body = kit.ok("fallback", kit.slots(), kit.latest("flights"));
        assertEquals(List.of("book a flight"), buttonTexts(body));
        Document log = kit.log("fallback");
        assertEquals("two_stage_fallback", log.get("type"));
        assertEquals(Kairon.SUCCESS, log.get("status"));
    }

    @Test
    void twoStageTextSearchReturnsAllMatchesUpToCount() {
        fallback(5);
        Map<String, Object> body = kit.ok("fallback", kit.slots(), kit.latest("flight"));
        assertEquals(List.of("book a flight", "flight status please"), buttonTexts(body));
    }

    @Test
    void twoStageTextSearchIsWordBasedNotSubstring() {
        fallback(5);
        Map<String, Object> body = kit.ok("fallback", kit.slots(), kit.latest("fli"));
        assertEquals(Kairon.UTTER_DEFAULT, kit.responses(body).get(0).get("response"));
    }

    @Test
    void memoryTextSearchFiltersAndScores() {
        fallback(5);
        List<Document> found = catalog.searchText("training_examples", kit.bot, "the hotel", 5);
        assertEquals(1, found.size());
        assertEquals("hotel booking", found.get(0).get("text"));
        assertTrue(found.get(0).get("_text_score") instanceof Double);
        assertEquals(List.of(), catalog.searchText("training_examples", kit.bot, "flight -book", 5).stream()
                .map(doc -> doc.get("text")).filter("book a flight"::equals).toList());
        assertEquals(List.of(), catalog.searchText("training_examples", kit.bot, "flight", 0));
    }

    // ---- T-030: google CSE request ----

    private void google(String apiKey, Object website) {
        kit.register("google", "google_search_action");
        kit.put("google_search_action", kit.doc("bot", kit.bot, "name", "google", "status", true,
                "api_key", kit.param("api_key", "value", apiKey), "search_engine_id", "asdfg::567890",
                "num_results", 1, "website", website, "failure_response", "I have failed to process your request",
                "dispatch_response", true));
    }

    private static Map<String, String> query(String raw) {
        Map<String, String> out = new LinkedHashMap<>();
        for (String pair : raw.split("&")) {
            String[] parts = pair.split("=", 2);
            out.put(URLDecoder.decode(parts[0], StandardCharsets.UTF_8),
                    parts.length > 1 ? URLDecoder.decode(parts[1], StandardCharsets.UTF_8) : "");
        }
        return out;
    }

    @Test
    void googleCseQueryMatchesPython() {
        google("KEY-1234", "https://nimblework.com");
        Map<String, Object> body = kit.ok("google", kit.slots(), kit.latest("what is kanban"));
        ParityKit.Hit hit = kit.hitPath("/customsearch/v1");
        assertEquals("GET", hit.method());
        Map<String, String> query = query(hit.query());
        assertEquals(List.of("q", "cx", "num", "key", "alt"), List.copyOf(query.keySet()));
        assertEquals("what is kanban", query.get("q"));
        assertEquals("asdfg::567890", query.get("cx"));
        assertEquals("1", query.get("num"));
        assertEquals("KEY-1234", query.get("key"));
        assertEquals("json", query.get("alt"));
        assertFalse(query.containsKey("siteSearch"), "Python pops website before the CSE call");
        assertTrue(kit.text(body).startsWith("S\nTo know more"));
        assertEquals(Kairon.SUCCESS, kit.log("google").get("status"));
    }

    @Test
    void googleKeylessPathBuildsSiteTermAndFailsClosed() {
        google("", "https://nimblework.com");
        Map<String, Object> body = kit.ok("google", kit.slots(), kit.latest("what is kanban?"));
        assertTrue(ParityKit.HITS.stream().noneMatch(hit -> hit.path().contains("/customsearch")));
        assertEquals("I have failed to process your request", kit.text(body));
        Document log = kit.log("google");
        assertEquals(Kairon.FAIL, log.get("status"));
        assertTrue(String.valueOf(log.get("exception")).contains("'what is kanban? site: https://nimblework.com'"),
                String.valueOf(log.get("exception")));
    }

    // ---- T-031: voice provider initiate-call ----

    private void voiceAction() {
        kit.register("call_me", "voice_call_action");
        kit.put("voice_call_action", kit.doc("bot", kit.bot, "name", "call_me", "status", true,
                "to_phone_number", kit.doc("parameter_type", "slot", "value", "phone")));
    }

    private void voiceChannel(String provider, boolean withToken) {
        Document config = kit.doc("telephony_provider", provider, "account_sid", tokens.encrypt("AC123"),
                "phone_number", "+15550000000", "call_url", "https://kairon.test/voice/call",
                "status_url", "https://kairon.test/voice/status");
        if (withToken) {
            config.put("auth_token", "twilio".equals(provider) ? tokens.encrypt("tok-secret") : "tok-secret");
        }
        kit.put("channels", kit.doc("bot", kit.bot, "connector_type", "voice", "config", config));
    }

    @Test
    void twilioInitiateCallRequestAndChannelLog() {
        voiceAction();
        voiceChannel("twilio", true);
        kit.pathBody("/Calls.json", "{\"sid\":\"CA999\",\"status\":\"queued\"}");
        Map<String, Object> body = kit.ok("call_me", kit.slots("phone", "+919999999999"), kit.latest("call me"));

        ParityKit.Hit hit = kit.hitPath("/Calls.json");
        assertEquals("POST", hit.method());
        assertEquals("/2010-04-01/Accounts/AC123/Calls.json", hit.path());
        assertEquals(HttpCaller.basic("AC123", "tok-secret"), hit.auth());
        Map<String, String> form = query(hit.body());
        assertEquals("+919999999999", form.get("To"));
        assertEquals("+15550000000", form.get("From"));
        assertEquals("https://kairon.test/voice/call", form.get("Url"));
        assertEquals("https://kairon.test/voice/status", form.get("StatusCallback"));
        assertEquals("POST", form.get("StatusCallbackMethod"));
        assertTrue(ParityKit.HITS.stream().noneMatch(h -> h.path().equals("/voice")), "generic voiceCallUrl not used");

        List<Document> channelLogs = catalog.all("channel_logs");
        assertEquals(1, channelLogs.size());
        Document log = channelLogs.get(0);
        assertEquals("voice", log.get("type"));
        assertEquals("initiated", log.get("status"));
        assertEquals(Map.of("to", "+919999999999", "call_sid", "CA999"), Map.copyOf((Map<String, Object>) log.get("data")));
        assertEquals("CA999", log.get("message_id"));
        assertEquals(kit.bot, log.get("bot"));
        assertEquals("system", log.get("user"));
        assertEquals("bot", log.get("initiator"));

        assertEquals("I'm placing a call to you now.", kit.text(body));
        assertEquals(Kairon.SUCCESS, kit.log("call_me").get("status"));
        assertEquals("voice_call_action", kit.log("call_me").get("type"));
    }

    @Test
    void twilioErrorFailsTheCall() {
        voiceAction();
        voiceChannel("twilio", true);
        kit.pathStatus("/Calls.json", 401);
        kit.pathBody("/Calls.json", "{\"code\":20003,\"message\":\"Authenticate\",\"status\":401}");
        Map<String, Object> body = kit.ok("call_me", kit.slots("phone", "+919999999999"), kit.latest("call me"));
        assertEquals(Kairon.CALL_FAIL, kit.text(body));
        Document log = kit.log("call_me");
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals("HTTP 401 error: Unable to create record: Authenticate", log.get("exception"));
        assertTrue(catalog.all("channel_logs").isEmpty());
    }

    @Test
    void missingAuthTokenIsKeyError() {
        voiceAction();
        voiceChannel("twilio", false);
        kit.ok("call_me", kit.slots("phone", "+919999999999"), kit.latest("call me"));
        assertEquals("'auth_token'", kit.log("call_me").get("exception"));
        assertTrue(ParityKit.HITS.isEmpty());
    }

    @Test
    void missingChannelFails() {
        voiceAction();
        kit.ok("call_me", kit.slots("phone", "+919999999999"), kit.latest("call me"));
        assertEquals("Channels matching query does not exist.", kit.log("call_me").get("exception"));
    }

    @Test
    void exotelInitiateCallRequest() {
        voiceAction();
        voiceChannel("exotel", true);
        kit.pathBody("/Calls/connect.json", "{\"Call\":{\"Sid\":\"EX42\"}}");
        kit.ok("call_me", kit.slots("phone", "+919999999999"), kit.latest("call me"));
        ParityKit.Hit hit = kit.hitPath("/Calls/connect.json");
        assertEquals("/v1/Accounts/AC123/Calls/connect.json", hit.path());
        assertEquals(HttpCaller.basic("AC123", "tok-secret"), hit.auth());
        Map<String, String> form = query(hit.body());
        assertEquals("+919999999999", form.get("From"));
        assertEquals("+15550000000", form.get("CallerId"));
        assertEquals("https://kairon.test/voice/call", form.get("Url"));
        assertEquals("https://kairon.test/voice/status", form.get("StatusCallback"));
        assertEquals("EX42", catalog.all("channel_logs").get(0).get("message_id"));
    }
}
