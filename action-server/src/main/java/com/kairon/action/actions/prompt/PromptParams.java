package com.kairon.action.actions.prompt;

import com.kairon.action.runtime.TrackerState;
import com.kairon.action.support.Maps;
import com.kairon.action.support.PyRepr;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Python ActionPrompt.__get_llm_params / __get_user_msg and ActionUtility.prepare_bot_responses
 * (kairon/actions/definitions/prompt.py, kairon/shared/actions/utils.py).
 *
 * <p>Config values follow the mongoengine defaults Python sees after {@code to_mongo()}:
 * {@code num_bot_responses} 5, {@code LlmPrompt.is_enabled} true, {@code LlmPrompt.source} static,
 * {@code process_media} false, {@code instructions} [].
 */
public final class PromptParams {

    public static final int DEFAULT_NUM_BOT_RESPONSES = 5;
    public static final int DEFAULT_TOP_RESULTS = 10;
    public static final double DEFAULT_SIMILARITY_THRESHOLD = 0.70;

    /**
     * Renders the context-prompt text for a user prompt whose source is not built in
     * (history, bot_content, slot). Hooks for {@code crud} and {@code action} plug in here;
     * a source without a hook falls back to the static {@code {name}:\n{data}\n} rendering.
     */
    @FunctionalInterface
    public interface ContextSource {
        String render(Map<String, Object> prompt);
    }

    /** Typed result of prompt assembly; {@link #toMap()} gives the Python {@code llm_params} dict. */
    public record LlmParams(
            String systemPrompt,
            String contextPrompt,
            String queryPrompt,
            boolean useQueryPrompt,
            List<Map<String, Object>> previousBotResponses,
            List<Map<String, Object>> similarityPrompt,
            Object hyperparameters,
            Object instructions,
            boolean shouldProcessMedia) {

        /** First similarity source's collection (the collection passed to predict), else null. */
        public String collection() {
            return similarityPrompt.isEmpty() ? null : Maps.str(similarityPrompt.get(0).get("collection"));
        }

        /** Python {@code params} key order; {@code query_prompt} is {} until a query prompt is enabled. */
        public Map<String, Object> toMap() {
            Map<String, Object> queryPromptDict = new LinkedHashMap<>();
            if (useQueryPrompt) {
                queryPromptDict.put("query_prompt", queryPrompt);
                queryPromptDict.put("use_query_prompt", true);
            }
            Map<String, Object> params = new LinkedHashMap<>();
            params.put("hyperparameters", hyperparameters);
            params.put("system_prompt", systemPrompt);
            params.put("context_prompt", contextPrompt);
            params.put("query_prompt", queryPromptDict);
            params.put("previous_bot_responses", previousBotResponses);
            params.put("similarity_prompt", similarityPrompt);
            params.put("instructions", instructions);
            return params;
        }
    }

    private PromptParams() {
    }

    public static LlmParams build(Map<String, Object> config, TrackerState tracker, Map<String, ContextSource> sources) {
        String systemPrompt = null;
        StringBuilder contextPrompt = new StringBuilder();
        StringBuilder queryPrompt = new StringBuilder();
        boolean useQueryPrompt = false;
        List<Map<String, Object>> history = null;
        List<Map<String, Object>> similarity = new ArrayList<>();
        int numBotResponses = config.get("num_bot_responses") instanceof Number number
                ? number.intValue() : DEFAULT_NUM_BOT_RESPONSES;
        for (Map<String, Object> prompt : Maps.mapList(config.get("llm_prompts"))) {
            if (!enabled(prompt)) {
                continue;
            }
            Object type = prompt.get("type");
            if ("system".equals(type)) {
                systemPrompt = PyRepr.str(prompt.get("data")) + "\n";
            } else if ("user".equals(type)) {
                String source = prompt.get("source") == null ? "static" : Maps.str(prompt.get("source"));
                switch (source) {
                    case "history" -> history = botResponses(tracker, numBotResponses);
                    case "bot_content" -> similarity.add(similaritySource(prompt));
                    case "slot" -> contextPrompt.append(section(prompt, tracker.slotValue(Maps.str(prompt.get("data")))));
                    default -> {
                        ContextSource hook = sources == null ? null : sources.get(source);
                        contextPrompt.append(hook != null ? hook.render(prompt) : section(prompt, prompt.get("data")));
                    }
                }
            } else if ("query".equals(type)) {
                queryPrompt.append(section(prompt, prompt.get("data")));
                useQueryPrompt = true;
            }
        }
        return new LlmParams(
                systemPrompt,
                contextPrompt.toString(),
                queryPrompt.toString(),
                useQueryPrompt,
                history,
                similarity,
                config.get("hyperparameters"),
                config.containsKey("instructions") ? config.get("instructions") : Collections.emptyList(),
                Maps.truthy(config.get("process_media")));
    }

    /** {@code {name}:\n{data}\n} plus the instructions block when the prompt has instructions. */
    public static String section(Map<String, Object> prompt, Object data) {
        return PyRepr.str(prompt.get("name")) + ":\n" + PyRepr.str(data) + "\n" + instructionsBlock(prompt);
    }

    /** {@code Instructions on how to use {name}:\n{instructions}\n\n} when instructions are truthy, else "". */
    public static String instructionsBlock(Map<String, Object> prompt) {
        Object instructions = prompt.get("instructions");
        if (!Maps.truthy(instructions)) {
            return "";
        }
        return "Instructions on how to use " + PyRepr.str(prompt.get("name")) + ":\n" + PyRepr.str(instructions) + "\n\n";
    }

    /**
     * Python __get_user_msg: {@code from_slot} returns the raw slot value; otherwise the latest text, where a
     * {@code /}-prefixed text is replaced by the {@code kairon_user_msg} entity when that entity is non-empty.
     */
    public static Object userQuestion(Map<String, Object> userQuestion, TrackerState tracker) {
        Map<String, Object> question = Maps.map(userQuestion);
        if ("from_slot".equals(question.get("type"))) {
            return tracker.slotValue(Maps.str(question.get("value")));
        }
        return tracker.userText();
    }

    /** Python ActionUtility.prepare_bot_responses: last {@code lastN} bot turns with their user turns, oldest first. */
    public static List<Map<String, Object>> botResponses(TrackerState tracker, int lastN) {
        List<Map<String, Object>> trail = new ArrayList<>();
        List<Map<String, Object>> events = tracker.copyEvents();
        int remaining = lastN;
        for (int index = events.size() - 1; index >= 0; index--) {
            Map<String, Object> event = events.get(index);
            Object kind = event.get("event");
            if ("bot".equals(kind) && Maps.truthy(event.get("text"))) {
                trail.add(0, message("assistant", event.get("text")));
                remaining -= 1;
            } else if ("user".equals(kind)) {
                if (!trail.isEmpty() && "user".equals(trail.get(0).get("role"))) {
                    trail.remove(0);
                }
                trail.add(0, message("user", event.get("text")));
                if (remaining <= 0) {
                    break;
                }
            } else if ("session_started".equals(kind)) {
                break;
            }
        }
        return trail;
    }

    private static boolean enabled(Map<String, Object> prompt) {
        return !prompt.containsKey("is_enabled") || Maps.truthy(prompt.get("is_enabled"));
    }

    private static Map<String, Object> similaritySource(Map<String, Object> prompt) {
        Map<String, Object> hyperparameters = Maps.map(prompt.get("hyperparameters"));
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("similarity_prompt_name", prompt.get("name"));
        item.put("similarity_prompt_instructions", prompt.get("instructions"));
        item.put("collection", prompt.get("data"));
        item.put("use_similarity_prompt", true);
        item.put("top_results", hyperparameters.containsKey("top_results")
                ? hyperparameters.get("top_results") : DEFAULT_TOP_RESULTS);
        item.put("similarity_threshold", hyperparameters.containsKey("similarity_threshold")
                ? hyperparameters.get("similarity_threshold") : DEFAULT_SIMILARITY_THRESHOLD);
        return item;
    }

    private static Map<String, Object> message(String role, Object content) {
        Map<String, Object> message = new LinkedHashMap<>();
        message.put("role", role);
        message.put("content", content);
        return message;
    }
}
