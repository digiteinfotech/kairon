package com.kairon.action.support.llm;

import com.kairon.action.ActionSettings;
import com.kairon.action.support.LlmHttp;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;

import java.nio.charset.StandardCharsets;
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

    public LlmClient(LlmHttp http, ActionSettings settings) {
        this.http = http;
        this.settings = settings;
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
