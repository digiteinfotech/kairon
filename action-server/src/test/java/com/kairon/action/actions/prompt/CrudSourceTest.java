package com.kairon.action.actions.prompt;

import com.kairon.action.ActionSettings;
import com.kairon.action.Kairon;
import com.kairon.action.actions.PromptAction;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.Dispatcher;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.catalog.ActionCatalog;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.TrackerState;
import com.kairon.action.support.Tokens;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** T-113: ActionPrompt crud source parity (prompt-db R3 c1-c10). */
class CrudSourceTest {

    private static final String BOT = "bot1";

    private MemoryActionCatalog catalog;
    private Tokens tokens;

    @BeforeEach
    void setUp() {
        catalog = new MemoryActionCatalog();
        ActionSettings settings = new ActionSettings();
        settings.setFernetKey("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=");
        tokens = new Tokens(settings);
    }

    // ---- fixtures ----

    private static Map<String, Object> map(Object... pairs) {
        Map<String, Object> map = new LinkedHashMap<>();
        for (int i = 0; i < pairs.length; i += 2) {
            map.put((String) pairs[i], pairs[i + 1]);
        }
        return map;
    }

    private static TrackerState tracker(Map<String, Object> slots) {
        Map<String, Object> tracker = new LinkedHashMap<>();
        tracker.put("sender_id", "u1");
        tracker.put("slots", slots);
        tracker.put("latest_message", map("text", "hi"));
        tracker.put("events", List.of());
        return TrackerState.from(tracker);
    }

    private void seed(String collection, Map<String, Object> data, List<String> secure, Map<String, Object> attrs) {
        List<Object> filterable = new ArrayList<>();
        attrs.forEach((k, v) -> filterable.add(new Document("k", k).append("v", v)));
        catalog.put(ActionCatalog.COGNITION_DATA, new Document("bot", BOT)
                .append("collection_name", collection)
                .append("is_secure", secure)
                .append("is_non_editable", List.of())
                .append("data", new Document(data))
                .append("filterable_attrs", filterable));
    }

    private static Map<String, Object> crudPrompt(Map<String, Object> crudConfig, Object instructions) {
        return map("type", "user", "source", "crud", "name", "Orders", "data", null,
                "instructions", instructions, "is_enabled", true, "crud_config", crudConfig);
    }

    private String render(Map<String, Object> prompt, Map<String, Object> slots) {
        return new CrudSource(catalog, tokens, BOT, tracker(slots)).render(prompt);
    }

    private String render(Map<String, Object> prompt) {
        return render(prompt, Map.of());
    }

    // ---- c1: config fields and defaults ----

    @Test
    void defaultsValueModeAndLimitTen() {
        for (int i = 0; i < 12; i++) {
            seed("orders", map("n", i), List.of(), map());
        }
        String out = render(crudPrompt(map("collections", List.of("orders")), null));
        StringBuilder expected = new StringBuilder("Collection data for Orders:\n[");
        for (int i = 0; i < 10; i++) {
            expected.append(i == 0 ? "" : ", ").append("{'n': ").append(i).append('}');
        }
        expected.append("]\n");
        assertEquals(expected.toString(), out);
    }

    @Test
    void resultLimitHonoured() {
        for (int i = 0; i < 5; i++) {
            seed("orders", map("n", i), List.of(), map());
        }
        String out = render(crudPrompt(map("collections", List.of("orders"), "result_limit", 2), null));
        assertEquals("Collection data for Orders:\n[{'n': 0}, {'n': 1}]\n", out);
    }

    @Test
    void noCollectionsNoInstructionsRendersNothing() {
        assertEquals("", render(crudPrompt(map(), null)));
        assertEquals("", render(map("type", "user", "source", "crud", "name", "x", "instructions", List.of())));
    }

    // ---- c2: slot mode dict / string / falsy ----

    @Test
    void slotModeDictUsedAsIs() {
        seed("orders", map("id", 1), List.of(), map("status", "open"));
        seed("orders", map("id", 2), List.of(), map("status", "closed"));
        String out = render(crudPrompt(map("collections", List.of("orders"), "query_source", "slot", "query", "q"), null),
                map("q", map("status", "open")));
        assertEquals("Collection data for Orders:\n[{'id': 1}]\n", out);
    }

    @Test
    void slotModeStringParsedAsJson() {
        seed("orders", map("id", 1), List.of(), map("status", "open"));
        seed("orders", map("id", 2), List.of(), map("status", "closed"));
        String out = render(crudPrompt(map("collections", List.of("orders"), "query_source", "slot", "query", "q"), null),
                map("q", "{\"status\": \"closed\"}"));
        assertEquals("Collection data for Orders:\n[{'id': 2}]\n", out);
    }

    @Test
    void slotModeFalsyMeansNoFilter() {
        seed("orders", map("id", 1), List.of(), map("status", "open"));
        seed("orders", map("id", 2), List.of(), map("status", "closed"));
        Map<String, Object> prompt = crudPrompt(map("collections", List.of("orders"), "query_source", "slot", "query", "q"), null);
        String all = "Collection data for Orders:\n[{'id': 1}, {'id': 2}]\n";
        assertEquals(all, render(prompt, map("q", "")));
        assertEquals(all, render(prompt, map()));
        assertEquals(all, render(prompt, map("q", map())));
    }

    // ---- c3: bad slot JSON ----

    @Test
    void slotModeBadJsonFails() {
        Map<String, Object> prompt = crudPrompt(map("collections", List.of("orders"), "query_source", "slot", "query", "q"), null);
        ActionFailure failure = assertThrows(ActionFailure.class, () -> render(prompt, map("q", "not json")));
        assertEquals("Invalid JSON format in slot value: not json", failure.getMessage());
        ActionFailure typeError = assertThrows(ActionFailure.class, () -> render(prompt, map("q", List.of("a"))));
        assertEquals("Invalid JSON format in slot value: ['a']", typeError.getMessage());
    }

    // ---- c4: value mode string parsed ----

    @Test
    void valueModeStringParsedAsJson() {
        seed("orders", map("id", 1), List.of(), map("status", "open"));
        seed("orders", map("id", 2), List.of(), map("status", "closed"));
        String out = render(crudPrompt(map("collections", List.of("orders"), "query", "{\"status\": \"open\"}"), null));
        assertEquals("Collection data for Orders:\n[{'id': 1}]\n", out);
        String dict = render(crudPrompt(map("collections", List.of("orders"), "query", map("status", "closed")), null));
        assertEquals("Collection data for Orders:\n[{'id': 2}]\n", dict);
    }

    // ---- c5: value mode bad JSON -> raw JSONDecodeError text ----

    @Test
    void valueModeBadJsonPropagatesRawParseError() {
        Map<String, Object> prompt = crudPrompt(map("collections", List.of("orders"), "query", "status=open"), null);
        ActionFailure failure = assertThrows(ActionFailure.class, () -> render(prompt));
        assertEquals("Expecting value: line 1 column 1 (char 0)", failure.getMessage());
        Map<String, Object> trailing = crudPrompt(map("collections", List.of("orders"), "query", "{} x"), null);
        assertEquals("Extra data: line 1 column 4 (char 3)",
                assertThrows(ActionFailure.class, () -> render(trailing)).getMessage());
    }

    @Test
    void valueModeBadJsonTakesGenericPromptFailurePath() {
        ActionSettings settings = new ActionSettings();
        settings.setFernetKey("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=");
        settings.setLlmUrl("http://127.0.0.1:1/llm");
        ActionSupport support = new ActionSupport(catalog, settings, tokens, null);
        catalog.put("bot_settings", new Document("bot", BOT).append("status", true)
                .append("llm_settings", new Document("enable_faq", true)));
        catalog.put("prompt_action", new Document("bot", BOT).append("name", "act").append("status", true)
                .append("failure_message", "sorry")
                // T-125: a missing hyperparameters field would load the LLMMetadata default at config load
                .append("hyperparameters", new Document("model", "gpt-4o-mini"))
                .append("llm_prompts", List.of(new Document(crudPrompt(
                        map("collections", List.of("orders"), "query", "status=open"), null)))));
        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("sender_id", "u1");
        raw.put("slots", new LinkedHashMap<>());
        raw.put("latest_message", map("text", "hi"));
        raw.put("events", List.of());
        ActionContext context = new ActionContext(BOT, "act", TrackerState.from(raw), new Dispatcher(), Map.of(), Map.of());
        // fails while building params, before LLMProcessor setup: no processor needed
        com.kairon.action.support.llm.LlmSecrets secrets = new com.kairon.action.support.llm.LlmSecrets(catalog, tokens);
        Map<String, Object> filled = new PromptAction(support, secrets,
                new com.kairon.action.support.llm.CognitionSchemas(catalog, secrets), null).execute(context);
        Document log = catalog.all(Kairon.LOGS).get(0);
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals("Expecting value: line 1 column 1 (char 0)", log.get("exception"));
        assertEquals("sorry", filled.get(Kairon.ACTION_RESPONSE));
    }

    // ---- c6: lowercased name, bot scope, AND of truthy pairs ----

    @Test
    void lowercasedNameBotScopeAndTruthyPairsAnded() {
        seed("orders", map("id", 1), List.of(), map("status", "open", "city", "pune"));
        seed("orders", map("id", 2), List.of(), map("status", "open", "city", "goa"));
        seed("other", map("id", 3), List.of(), map("status", "open", "city", "pune"));
        catalog.put(ActionCatalog.COGNITION_DATA, new Document("bot", "bot2").append("collection_name", "orders")
                .append("is_secure", List.of()).append("data", new Document("id", 4))
                .append("filterable_attrs", List.of(new Document("k", "status").append("v", "open"))));
        String out = render(crudPrompt(map("collections", List.of("ORDERS"),
                "query", map("status", "open", "city", "pune", "empty", "", "zero", 0)), null));
        assertEquals("Collection data for Orders:\n[{'id': 1}]\n", out);
    }

    @Test
    void recordsHelperDropsFalsyPairs() {
        seed("orders", map("id", 1), List.of(), map("status", "open"));
        CrudSource source = new CrudSource(catalog, tokens, BOT, tracker(Map.of()));
        List<Object> data = source.records("Orders", List.of("status", "", "x"), List.of("open", "v", ""), 10);
        assertEquals(List.of(Map.of("id", 1)), data);
    }

    // ---- c7: data only, decrypted when secure ----

    @Test
    void onlyDataUsedAndSecureKeysDecrypted() {
        seed("orders", map("user", "ann", "card", tokens.encrypt("4111"), "n", 3), List.of("card"), map());
        String out = render(crudPrompt(map("collections", List.of("orders")), null));
        assertEquals("Collection data for Orders:\n[{'user': 'ann', 'card': '4111', 'n': 3}]\n", out);
    }

    // ---- c8: key/value length mismatch ----

    @Test
    void keyValueLengthMismatchFails() {
        CrudSource source = new CrudSource(catalog, tokens, BOT, tracker(Map.of()));
        ActionFailure failure = assertThrows(ActionFailure.class,
                () -> source.records("orders", List.of("a", "b"), List.of("x"), 10));
        assertEquals("Keys and values lists must be of the same length.", failure.getMessage());
    }

    // ---- c9 + c10: per-collection blocks, instructions once ----

    @Test
    void perCollectionBlocksThenInstructionsOnce() {
        seed("orders", map("id", 1), List.of(), map());
        seed("items", map("sku", "a"), List.of(), map());
        String out = render(crudPrompt(map("collections", List.of("orders", "items", "none")), "use it"));
        assertEquals("Collection data for Orders:\n[{'id': 1}]\n"
                + "Collection data for Orders:\n[{'sku': 'a'}]\n"
                + "Collection data for Orders:\n[]\n"
                + "Instructions on how to use collection Orders:\nuse it\n\n", out);
    }

    @Test
    void registeredAsCrudHookInPromptParams() {
        seed("orders", map("id", 1), List.of(), map());
        Map<String, Object> config = map("llm_prompts", List.of(crudPrompt(map("collections", List.of("orders")), null)));
        TrackerState tracker = tracker(Map.of());
        PromptParams.LlmParams params = PromptParams.build(config, tracker,
                Map.of("crud", new CrudSource(catalog, tokens, BOT, tracker)));
        assertTrue(params.contextPrompt().startsWith("Collection data for Orders:\n[{'id': 1}]\n"));
    }
}
