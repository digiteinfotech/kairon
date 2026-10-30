package com.kairon.action.actions.prompt;

import com.kairon.action.runtime.TrackerState;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** T-105: ActionPrompt.__get_llm_params / __get_user_msg parity (prompt-db R2 c1-c11). */
class PromptParamsTest {

    // ---- fixtures ----

    private static Map<String, Object> map(Object... pairs) {
        Map<String, Object> map = new LinkedHashMap<>();
        for (int i = 0; i < pairs.length; i += 2) {
            map.put((String) pairs[i], pairs[i + 1]);
        }
        return map;
    }

    private static TrackerState tracker(Map<String, Object> slots, Map<String, Object> latest, List<Map<String, Object>> events) {
        Map<String, Object> tracker = new LinkedHashMap<>();
        tracker.put("sender_id", "u1");
        tracker.put("slots", slots);
        tracker.put("latest_message", latest);
        tracker.put("events", events);
        return TrackerState.from(tracker);
    }

    private static TrackerState tracker() {
        return tracker(Map.of(), map("text", "hi"), List.of());
    }

    private static Map<String, Object> prompt(String type, String source, String name, Object data, Object instructions) {
        Map<String, Object> prompt = map("type", type, "name", name, "data", data, "instructions", instructions, "is_enabled", true);
        if (source != null) {
            prompt.put("source", source);
        }
        return prompt;
    }

    private static Map<String, Object> config(List<Map<String, Object>> prompts) {
        return map("llm_prompts", prompts, "hyperparameters", map("model", "gpt-4o-mini"));
    }

    private static PromptParams.LlmParams build(Map<String, Object> config, TrackerState tracker) {
        return PromptParams.build(config, tracker, Map.of());
    }

    private static Map<String, Object> user(String text) {
        return map("event", "user", "text", text);
    }

    private static Map<String, Object> bot(String text) {
        return map("event", "bot", "text", text);
    }

    // ---- c1: enabled prompts in config order ----

    @Test
    void disabledPromptsSkippedAndOrderKept() {
        Map<String, Object> disabled = prompt("user", "static", "skip", "nope", null);
        disabled.put("is_enabled", false);
        Map<String, Object> implicit = prompt("user", "static", "third", "c", null);
        implicit.remove("is_enabled"); // mongoengine default is_enabled=True
        PromptParams.LlmParams params = build(config(List.of(
                prompt("user", "static", "first", "a", null),
                disabled,
                prompt("user", "static", "second", "b", null),
                implicit)), tracker());
        assertEquals("first:\na\nsecond:\nb\nthird:\nc\n", params.contextPrompt());
    }

    // ---- c2: system prompt ----

    @Test
    void systemPromptLastWins() {
        PromptParams.LlmParams params = build(config(List.of(
                prompt("system", null, "s1", "first system", null),
                prompt("system", null, "s2", "second system", null))), tracker());
        assertEquals("second system\n", params.systemPrompt());
    }

    @Test
    void noSystemPromptIsNull() {
        assertNull(build(config(List.of()), tracker()).systemPrompt());
    }

    // ---- c3: query prompts ----

    @Test
    void queryPromptsAccumulateWithInstructionsAndEnable() {
        PromptParams.LlmParams params = build(config(List.of(
                prompt("query", null, "q1", "rephrase", "be brief"),
                prompt("query", null, "q2", "translate", null))), tracker());
        assertEquals("q1:\nrephrase\nInstructions on how to use q1:\nbe brief\n\nq2:\ntranslate\n", params.queryPrompt());
        assertTrue(params.useQueryPrompt());
        assertEquals(map("query_prompt", params.queryPrompt(), "use_query_prompt", true), params.toMap().get("query_prompt"));
    }

    @Test
    void noQueryPromptGivesEmptyDict() {
        PromptParams.LlmParams params = build(config(List.of()), tracker());
        assertFalse(params.useQueryPrompt());
        assertEquals(Map.of(), params.toMap().get("query_prompt"));
    }

    // ---- c4 / c5: history ----

    private static List<Map<String, Object>> conversation(int turns) {
        List<Map<String, Object>> events = new ArrayList<>();
        events.add(user("old"));
        events.add(bot("old-reply"));
        events.add(map("event", "session_started"));
        for (int i = 1; i <= turns; i++) {
            events.add(user("u" + i));
            events.add(map("event", "action", "name", "action_listen"));
            events.add(bot("b" + i));
        }
        return events;
    }

    private static List<Map<String, Object>> trail(int from, int to) {
        List<Map<String, Object>> trail = new ArrayList<>();
        for (int i = from; i <= to; i++) {
            trail.add(map("role", "user", "content", "u" + i));
            trail.add(map("role", "assistant", "content", "b" + i));
        }
        return trail;
    }

    @Test
    void historyDefaultsToFiveBotTurns() {
        TrackerState tracker = tracker(Map.of(), map("text", "u7"), conversation(7));
        PromptParams.LlmParams params = build(config(List.of(prompt("user", "history", "h", null, null))), tracker);
        assertEquals(trail(3, 7), params.previousBotResponses());
    }

    @Test
    void historyHonoursNumBotResponses() {
        Map<String, Object> config = config(List.of(prompt("user", "history", "h", null, null)));
        config.put("num_bot_responses", 2);
        TrackerState tracker = tracker(Map.of(), map("text", "u7"), conversation(7));
        assertEquals(trail(6, 7), build(config, tracker).previousBotResponses());
    }

    @Test
    void historyStopsAtSessionStartOldestFirst() {
        TrackerState tracker = tracker(Map.of(), map("text", "u2"), conversation(2));
        List<Map<String, Object>> history = build(config(List.of(prompt("user", "history", "h", null, null))), tracker)
                .previousBotResponses();
        assertEquals(trail(1, 2), history);
    }

    @Test
    void consecutiveUserTurnsKeepOnlyTheEarliest() {
        List<Map<String, Object>> events = List.of(user("u1"), bot("b1"), user("u2a"), user("u2b"), bot("b2"));
        List<Map<String, Object>> history = PromptParams.botResponses(tracker(Map.of(), map(), events), 5);
        assertEquals(List.of(
                map("role", "user", "content", "u1"), map("role", "assistant", "content", "b1"),
                map("role", "user", "content", "u2a"), map("role", "assistant", "content", "b2")), history);
    }

    @Test
    void noHistoryPromptIsNull() {
        assertNull(build(config(List.of()), tracker()).previousBotResponses());
        assertNull(build(config(List.of()), tracker()).toMap().get("previous_bot_responses"));
    }

    // ---- c6: bot_content ----

    @Test
    void botContentAddsSimilaritySourceWithDefaults() {
        PromptParams.LlmParams params = build(config(List.of(
                prompt("user", "bot_content", "kb", "faq_docs", "cite sources"))), tracker());
        assertEquals(List.of(map(
                "similarity_prompt_name", "kb",
                "similarity_prompt_instructions", "cite sources",
                "collection", "faq_docs",
                "use_similarity_prompt", true,
                "top_results", 10,
                "similarity_threshold", 0.70)), params.similarityPrompt());
        assertEquals("faq_docs", params.collection());
        assertEquals("", params.contextPrompt());
    }

    @Test
    void botContentHyperparametersOverrideDefaults() {
        Map<String, Object> kb = prompt("user", "bot_content", "kb", "default", null);
        kb.put("hyperparameters", map("top_results", 3, "similarity_threshold", 0.5));
        Map<String, Object> second = prompt("user", "bot_content", "kb2", "other", null);
        PromptParams.LlmParams params = build(config(List.of(kb, second)), tracker());
        assertEquals(2, params.similarityPrompt().size());
        assertEquals(3, params.similarityPrompt().get(0).get("top_results"));
        assertEquals(0.5, params.similarityPrompt().get(0).get("similarity_threshold"));
        assertEquals("default", params.collection());
    }

    @Test
    void noSimilaritySourceHasNoCollection() {
        PromptParams.LlmParams params = build(config(List.of()), tracker());
        assertEquals(List.of(), params.similarityPrompt());
        assertNull(params.collection());
    }

    // ---- c7: slot ----

    @Test
    void slotSourceRendersValueAndNone() {
        Map<String, Object> slots = new HashMap<>();
        slots.put("city", "Pune");
        slots.put("empty", null);
        slots.put("items", List.of("a", 1));
        PromptParams.LlmParams params = build(config(List.of(
                prompt("user", "slot", "City", "city", null),
                prompt("user", "slot", "Empty", "empty", null),
                prompt("user", "slot", "Missing", "absent", null),
                prompt("user", "slot", "Items", "items", null))), tracker(slots, map("text", "hi"), List.of()));
        assertEquals("City:\nPune\nEmpty:\nNone\nMissing:\nNone\nItems:\n['a', 1]\n", params.contextPrompt());
    }

    // ---- c8 / c9: other sources and instructions ----

    @Test
    void otherSourceAppendsNameAndData() {
        PromptParams.LlmParams params = build(config(List.of(prompt("user", "static", "Ctx", "some text", null))), tracker());
        assertEquals("Ctx:\nsome text\n", params.contextPrompt());
    }

    @Test
    void missingSourceDefaultsToStatic() {
        PromptParams.LlmParams params = build(config(List.of(prompt("user", null, "Ctx", "x", null))), tracker());
        assertEquals("Ctx:\nx\n", params.contextPrompt());
    }

    @Test
    void contextSourcesAppendInstructionsBlock() {
        PromptParams.LlmParams params = build(config(List.of(
                prompt("user", "static", "Ctx", "x", "use it"),
                prompt("user", "slot", "S", "s", "slot rules"),
                prompt("user", "static", "Blank", "y", " "))),
                tracker(map("s", "v"), map("text", "hi"), List.of()));
        assertEquals("Ctx:\nx\nInstructions on how to use Ctx:\nuse it\n\n"
                + "S:\nv\nInstructions on how to use S:\nslot rules\n\n"
                + "Blank:\ny\nInstructions on how to use Blank:\n \n\n", params.contextPrompt());
    }

    @Test
    void crudAndActionSourcesUseRegisteredHooks() {
        Map<String, PromptParams.ContextSource> hooks = Map.of(
                "crud", prompt -> "CRUD[" + prompt.get("name") + "]\n",
                "action", prompt -> "ACTION[" + prompt.get("data") + "]\n");
        PromptParams.LlmParams params = PromptParams.build(config(List.of(
                prompt("user", "crud", "orders", null, null),
                prompt("user", "static", "s", "t", null),
                prompt("user", "action", "act", "nested_action", null))), tracker(), hooks);
        assertEquals("CRUD[orders]\ns:\nt\nACTION[nested_action]\n", params.contextPrompt());
    }

    // ---- c10: hyperparameters, instructions, should_process_media ----

    @Test
    void hyperparametersInstructionsAndMediaFlagReachParams() {
        Map<String, Object> config = config(List.of());
        config.put("instructions", List.of("be concise"));
        config.put("process_media", true);
        PromptParams.LlmParams params = build(config, tracker());
        assertEquals(map("model", "gpt-4o-mini"), params.hyperparameters());
        assertEquals(List.of("be concise"), params.instructions());
        assertTrue(params.shouldProcessMedia());
        Map<String, Object> asMap = params.toMap();
        assertEquals(List.of("hyperparameters", "system_prompt", "context_prompt", "query_prompt",
                "previous_bot_responses", "similarity_prompt", "instructions"), new ArrayList<>(asMap.keySet()));
        assertEquals(map("model", "gpt-4o-mini"), asMap.get("hyperparameters"));
        assertEquals(List.of("be concise"), asMap.get("instructions"));
    }

    @Test
    void instructionsAndMediaDefaults() {
        PromptParams.LlmParams params = build(config(List.of()), tracker());
        assertEquals(List.of(), params.instructions());
        assertFalse(params.shouldProcessMedia());
    }

    // ---- c11: user question ----

    @Test
    void userQuestionFromSlotUsesRawSlotValue() {
        TrackerState tracker = tracker(map("q", "slot question", "n", 42), map("text", "typed"), List.of());
        assertEquals("slot question", PromptParams.userQuestion(map("type", "from_slot", "value", "q"), tracker));
        assertEquals(42, PromptParams.userQuestion(map("type", "from_slot", "value", "n"), tracker));
    }

    @Test
    void userQuestionDefaultsToLatestText() {
        TrackerState tracker = tracker(Map.of(), map("text", "typed"), List.of());
        assertEquals("typed", PromptParams.userQuestion(map("type", "from_user_message"), tracker));
        assertEquals("typed", PromptParams.userQuestion(null, tracker));
    }

    @Test
    void userQuestionSlashTextReplacedByKaironUserMsgEntity() {
        TrackerState withEntity = tracker(Map.of(), map("text", "/ask",
                "entities", List.of(map("entity", "kairon_user_msg", "value", "real question"))), List.of());
        assertEquals("real question", PromptParams.userQuestion(map("type", "from_user_message"), withEntity));
        TrackerState noEntity = tracker(Map.of(), map("text", "/ask"), List.of());
        assertEquals("/ask", PromptParams.userQuestion(map("type", "from_user_message"), noEntity));
    }
}
