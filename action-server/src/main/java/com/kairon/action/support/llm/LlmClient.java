package com.kairon.action.support.llm;

import com.kairon.action.ActionSettings;
import com.kairon.action.support.LlmHttp;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.support.Maps;
import com.kairon.action.support.PyRepr;
import com.kairon.action.support.TokenTruncator;
import jakarta.inject.Inject;
import jakarta.inject.Singleton;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Client for the kairon LLM server, mirroring kairon/shared/llm/processor.py LLMProcessor.
 * Transport (headers, timeout, single attempt, status phrases) is {@link LlmHttp}.
 *
 * <p>Seams: embedding ({@code __get_embedding}, T-117) and message building / rephrase / perplexity
 * ({@code __get_answer}, {@code __rephrase_query}, T-118) are added beside {@link #complete}.
 */
@Singleton
public class LlmClient {

    /** One completion: {@code (formatted_response, response)} from {@code __get_completion}. */
    public record Completion(Object content, Object raw) {
        /**
         * {@code raw.get("litellm_call_id") or raw.get("openrouter_call_id")} when raw is a dict, else None.
         */
        public Object callId() {
            if (!(raw instanceof Map<?, ?> response)) {
                return null;
            }
            Object litellm = response.get("litellm_call_id");
            return Maps.truthy(litellm) ? litellm : response.get("openrouter_call_id");
        }
    }

    private final LlmHttp http;
    private final ActionSettings settings;
    private final CognitionSchemas schemas;

    @Inject
    public LlmClient(LlmHttp http, ActionSettings settings, CognitionSchemas schemas) {
        this.http = http;
        this.settings = settings;
        this.schemas = schemas;
    }

    /** Completion-only client (no cognition schema lookup); {@link #embed} is unavailable. */
    public LlmClient(LlmHttp http, ActionSettings settings) {
        this(http, settings, null);
    }

    /**
     * processor.py {@code get_embedding} for one text: sent as a one-element {@code text} list; a list
     * response yields its first element (IndexError text when empty), anything else is returned as-is.
     */
    public Object embed(String bot, String llmType, String text, Object user, Object invocation, String collection,
                        Map<String, String> embeddingSecret) {
        Object response = embedAll(bot, llmType, List.of(text), user, invocation, collection, embeddingSecret);
        if (response instanceof List<?> list) {
            if (list.isEmpty()) {
                throw new ActionFailure("list index out of range");
            }
            return list.get(0);
        }
        return response;
    }

    /**
     * processor.py {@code get_embedding} for a list: POST {@code {llm.url}/{quote(bot)}/aembedding/{llm_type}} with
     * body {@code {text, user, kwargs}}; kwargs keys in Python order {@code invocation}, then {@code collection} and
     * {@code model} (schema model_id) only when the collection's schema has training_needed false (missing schema
     * = true), then {@code truncated_texts} (8191 cl100k_base tokens each) and {@code api_key} (embedding secret).
     * The full response is returned. Status outside 200-204 and transport errors fail via {@link LlmHttp#post}.
     */
    public Object embedAll(String bot, String llmType, List<String> texts, Object user, Object invocation,
                           String collection, Map<String, String> embeddingSecret) {
        if (schemas == null) {
            throw new IllegalStateException("LlmClient built without CognitionSchemas cannot embed");
        }
        CognitionSchemas.Schema schema = schemas.forEmbedding(bot, collection);
        Map<String, Object> kwargs = new LinkedHashMap<>();
        kwargs.put("invocation", invocation);
        if (!schema.trainingNeeded()) {
            kwargs.put("collection", collection);
            kwargs.put("model", schema.modelId());
        }
        List<String> truncated = new ArrayList<>(texts.size());
        for (String text : texts) {
            truncated.add(TokenTruncator.truncate(text, TokenTruncator.EMBEDDING_CTX_LENGTH));
        }
        kwargs.put("truncated_texts", truncated);
        kwargs.put("api_key", embeddingSecret == null ? null : embeddingSecret.get("api_key"));
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("text", texts);
        body.put("user", user);
        body.put("kwargs", kwargs);
        return http.post(url(bot, "aembedding", llmType), body);
    }

    /**
     * processor.py {@code __get_completion}: POST {@code {llm.url}/{quote(bot)}/completion/{llm_type}} with body
     * {@code messages, hyperparameters, user, invocation, media_ids ([] when falsy), should_process_media}.
     * A dict response yields {@code (formatted_response, response)}; anything else is returned as both.
     * Status outside 200-204 and transport errors fail via {@link LlmHttp#post}.
     */
    public Completion complete(String bot, String llmType, List<?> messages, Object hyperparameters, Object user,
                               Object invocation, List<?> mediaIds, boolean shouldProcessMedia) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("messages", messages);
        body.put("hyperparameters", hyperparameters);
        body.put("user", user);
        body.put("invocation", invocation);
        body.put("media_ids", mediaIds == null || mediaIds.isEmpty() ? List.of() : mediaIds);
        body.put("should_process_media", shouldProcessMedia);
        Object response = http.post(url(bot, "completion", llmType), body);
        if (response instanceof Map<?, ?> map) {
            return new Completion(map.get("formatted_response"), map.get("response"));
        }
        return new Completion(response, response);
    }

    /** Answer content and call id from processor.py {@code __get_answer}. */
    public record Answer(Object content, Object callId) {
    }

    /** {@link #answer(AnswerParams, List)} discarding the per-completion logs. */
    public Answer answer(AnswerParams params) {
        return answer(params, new ArrayList<>());
    }

    /**
     * processor.py {@code __get_answer}: an optional rephrase completion ({@code __rephrase_query}) then the main
     * completion. Each completion appends {@code {messages, raw_completion_response, type, hyperparameters}}
     * ({@code rephrase_query} / {@code answer_query}) to {@code logs} as soon as it returns, so logs survive a
     * later failure.
     */
    public Answer answer(AnswerParams params, List<Map<String, Object>> logs) {
        Object query = params.query();
        Object hyperparameters = params.hyperparameters();
        String instructions = joinInstructions(params.instructions());
        if (params.useQueryPrompt() && params.queryPrompt() != null && !params.queryPrompt().isEmpty()) {
            List<Map<String, Object>> rephrase = List.of(
                    message("system", params.systemPrompt()),
                    message("user", params.queryPrompt() + "\n\n Q: " + PyRepr.str(query) + "\n A:"));
            Completion completion = complete(params.bot(), params.endpointLlmType(), rephrase, hyperparameters,
                    params.user(), PyRepr.str(params.invocation()) + "_rephrase", null, false);
            logs.add(log(rephrase, completion.raw(), "rephrase_query", hyperparameters));
            query = completion.content();
        }
        List<Map<String, Object>> messages = new ArrayList<>();
        messages.add(message("system", params.systemPrompt()));
        if (params.previousBotResponses() != null && !params.previousBotResponses().isEmpty()) {
            messages.addAll(params.previousBotResponses());
        }
        query = modifyUserMessageForPerplexity(query, params.llmType(), hyperparameters);
        String context = PyRepr.str(params.context());
        messages.add(message("user", instructions.isEmpty()
                ? context + " \nQ: " + PyRepr.str(query) + " \nA:"
                : context + " \n" + instructions + " \nQ: " + PyRepr.str(query) + " \nA:"));
        Completion completion = complete(params.bot(), params.endpointLlmType(), messages, hyperparameters,
                params.user(), params.invocation(), params.mediaIds(), params.shouldProcessMedia());
        logs.add(log(messages, completion.raw(), "answer_query", hyperparameters));
        return new Answer(completion.content(), completion.callId());
    }

    /**
     * processor.py {@code modify_user_message_for_perplexity}: for {@code perplexity} with a truthy
     * {@code search_domain_filter}, appends {@code " inurl:" + "|".join(stripped non-blank domains)}.
     */
    public static Object modifyUserMessageForPerplexity(Object userMessage, String llmType, Object hyperparameters) {
        if (!"perplexity".equals(llmType)) {
            return userMessage;
        }
        Object filter = Maps.map(hyperparameters).get("search_domain_filter");
        if (!Maps.truthy(filter)) {
            return userMessage;
        }
        List<String> domains = new ArrayList<>();
        for (Object domain : Maps.list(filter)) {
            String stripped = PyRepr.str(domain).strip();
            if (!stripped.isEmpty()) {
                domains.add(stripped);
            }
        }
        return PyRepr.str(userMessage) + " inurl:" + String.join("|", domains);
    }

    /** {@code '\n'.join(instructions)}: a string joins its characters, null reads as []. */
    static String joinInstructions(Object instructions) {
        if (instructions == null) {
            return "";
        }
        if (instructions instanceof String text) {
            return String.join("\n", text.codePoints().mapToObj(Character::toString).toList());
        }
        List<String> parts = new ArrayList<>();
        for (Object item : Maps.list(instructions)) {
            parts.add(PyRepr.str(item));
        }
        return String.join("\n", parts);
    }

    private static Map<String, Object> message(String role, Object content) {
        Map<String, Object> message = new LinkedHashMap<>();
        message.put("role", role);
        message.put("content", content);
        return message;
    }

    private static Map<String, Object> log(List<Map<String, Object>> messages, Object raw, String type,
                                           Object hyperparameters) {
        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("messages", messages);
        entry.put("raw_completion_response", raw);
        entry.put("type", type);
        entry.put("hyperparameters", hyperparameters);
        return entry;
    }

    /** {@code f"{llm.url}/{urllib.parse.quote(bot)}/{endpoint}/{llm_type}"}. */
    String url(String bot, String endpoint, String llmType) {
        return settings.getLlmServerUrl() + "/" + quote(bot) + "/" + endpoint + "/" + llmType;
    }

    /** urllib.parse.quote(text) with the default safe '/': unreserved and '/' kept, other UTF-8 bytes %XX. */
    public static String quote(String text) {
        StringBuilder out = new StringBuilder();
        for (byte b : String.valueOf(text).getBytes(StandardCharsets.UTF_8)) {
            int c = b & 0xff;
            if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')
                    || c == '_' || c == '.' || c == '-' || c == '~' || c == '/') {
                out.append((char) c);
            } else {
                out.append('%').append(String.format("%02X", c));
            }
        }
        return out.toString();
    }
}
