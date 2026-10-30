package com.kairon.action.support.llm;

import com.kairon.action.ActionSettings;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.support.HttpCaller;
import com.kairon.action.support.LlmHttp;
import jakarta.inject.Singleton;

import java.net.URI;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Qdrant calls made by kairon/shared/llm/processor.py LLMProcessor. Search mirrors
 * {@code __collection_search__} + {@code _process_similarity_prompt}: AioRestClient POST with
 * {@code self.headers} ({@code api-key} only when {@code vector.key} is set), {@code timeout=5},
 * one attempt (max_retries=1), raise_for_status.
 */
@Singleton
public class QdrantClient {

    /** processor.py: `timeout=5` on every Qdrant call of the similarity search. */
    static final int SEARCH_TIMEOUT_SECONDS = 5;
    private static final String SUFFIX = "_faq_embd";

    private final HttpCaller http;
    private final ActionSettings settings;

    public QdrantClient(HttpCaller http, ActionSettings settings) {
        this.http = http;
        this.settings = settings;
    }

    /**
     * Searches one similarity source and returns {@code search_result['result']} (the hit list).
     * A response without {@code result} fails, as Python's {@code search_result['result']} raises KeyError.
     */
    public List<?> search(String bot, Map<String, ?> source, List<?> vector) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("vector", vector);
        body.put("limit", get(source, "top_results", 10));
        body.put("with_payload", true);
        body.put("score_threshold", get(source, "similarity_threshold", 0.70));
        String url = join(settings.getVectorDb(), "/collections/" + collectionName(bot, source.get("collection")) + "/points/search");
        HttpCaller.Exchange exchange = http.exchange("POST", url, headers(), body, "json", SEARCH_TIMEOUT_SECONDS);
        if (exchange.transportFailed()) {
            throw new ActionFailure(exchange.error());
        }
        if (exchange.status() >= 400) {
            // aiohttp raise_for_status (status >= 400) -> ClientResponseError, wrapped by AioRestClient's catch-all.
            throw new ActionFailure("Failed to execute the url: " + exchange.status() + ", message='"
                    + LlmHttp.phrase(exchange.status()) + "', url='" + url + "'");
        }
        if (!(exchange.body() instanceof Map<?, ?> response)) {
            throw new ActionFailure("Attempt to decode JSON with unexpected mimetype: " + url);
        }
        if (!response.containsKey("result")) {
            throw new ActionFailure("'result'");
        }
        Object result = response.get("result");
        if (result == null) {
            throw new ActionFailure("'NoneType' object is not iterable");
        }
        if (!(result instanceof List<?> hits)) {
            throw new ActionFailure("Qdrant search result is not a list: " + result);
        }
        return hits;
    }

    /** `{bot}_faq_embd` for the `default` collection, else `{bot}_{collection}_faq_embd`. */
    public static String collectionName(String bot, Object collection) {
        if ("default".equals(collection)) {
            return bot + SUFFIX;
        }
        return bot + "_" + (collection == null ? "None" : collection) + SUFFIX;
    }

    /** `{"api-key": vector.key}` when the key is set, else no headers. */
    Map<String, Object> headers() {
        Map<String, Object> headers = new LinkedHashMap<>();
        String key = settings.getVectorKey();
        if (key != null && !key.isEmpty()) {
            headers.put("api-key", key);
        }
        return headers;
    }

    /** Python dict.get(key, default): the default applies only when the key is absent. */
    private static Object get(Map<String, ?> source, String key, Object fallback) {
        return source.containsKey(key) ? source.get(key) : fallback;
    }

    /** urllib.parse.urljoin(base, absolute_path): keeps scheme and authority, replaces the path. */
    static String join(String base, String path) {
        URI uri = URI.create(base);
        if (uri.getScheme() == null || uri.getRawAuthority() == null) {
            return base + path;
        }
        return uri.getScheme() + "://" + uri.getRawAuthority() + path;
    }
}
