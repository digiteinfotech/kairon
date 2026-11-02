package com.kairon.action.support.llm;

import com.kairon.action.ActionSettings;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.support.HttpCaller;
import com.kairon.action.support.LlmHttp;
import com.kairon.action.support.Maps;
import jakarta.inject.Inject;
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
 *
 * <p>{@link #query} mirrors kairon/shared/vector_embeddings/db/qdrant.py {@code Qdrant.perform_operation}
 * for database_action.
 */
@Singleton
public class QdrantClient {

    /** processor.py: `timeout=5` on every Qdrant call of the similarity search. */
    static final int SEARCH_TIMEOUT_SECONDS = 5;
    private static final String SUFFIX = "_faq_embd";

    /** qdrant.py {@code __get_embedding}: the embedding invocation of a database_action point query. */
    static final String QUERY_INVOCATION = "db_action_qdrant";
    static final String NO_OPERATION = "No Operation to perform";

    private final HttpCaller http;
    private final ActionSettings settings;
    private final LlmClient llm;

    @Inject
    public QdrantClient(HttpCaller http, ActionSettings settings, LlmClient llm) {
        this.http = http;
        this.settings = settings;
        this.llm = llm;
    }

    /** Search-only client (no embedding); {@link #query} with {@code embedding_search} is unavailable. */
    public QdrantClient(HttpCaller http, ActionSettings settings) {
        this(http, settings, null);
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

    /**
     * qdrant.py {@code perform_operation}: POST {@code urljoin(vector.db, /collections/{bot}_{collection}_faq_embd/points/query)}.
     * A non-empty string {@code embedding_search} becomes {@code query} (its embedding, invocation
     * {@code db_action_qdrant}); a truthy {@code payload_search} is merged at top level; then
     * {@code with_payload: true} and {@code limit: 10} when absent. An empty request fails with
     * {@code No Operation to perform}. Sent via ActionUtility.execute_http_request ({@link HttpCaller#executeStrict}):
     * no {@code api-key} header (Python passes no headers), {@code action.request_timeout}, non-2xx/transport
     * errors as {@code Failed to execute the url: ...}; the JSON (or text) response is returned unmodified.
     *
     * @param llmType         LLMProcessor llm_type (openai, or openrouter after the database_action swap)
     * @param embeddingSecret LLMProcessor llm_secret_embedding
     * @param user            tracker sender id
     */
    public Object query(String bot, String collection, Object payload, String llmType,
                        Map<String, String> embeddingSecret, Object user) {
        Map<String, Object> request = new LinkedHashMap<>();
        if (payload instanceof Map<?, ?> data) {
            if (data.get("embedding_search") instanceof String text && !text.isEmpty()) {
                if (llm == null) {
                    throw new IllegalStateException("QdrantClient built without LlmClient cannot embed");
                }
                request.put("query", llm.embed(bot, llmType, text, user, QUERY_INVOCATION, collection, embeddingSecret));
            }
            Object search = data.get("payload_search");
            if (Maps.truthy(search)) {
                if (!(search instanceof Map<?, ?> fields)) {
                    throw new ActionFailure("dict.update() argument after ** must be a mapping, not " + pythonType(search));
                }
                fields.forEach((key, value) -> request.put(String.valueOf(key), value));
            }
        }
        if (request.isEmpty()) {
            throw new ActionFailure(NO_OPERATION);
        }
        request.put("with_payload", true);
        if (!request.containsKey("limit")) {
            request.put("limit", 10);
        }
        String url = join(settings.getVectorDb(), "/collections/" + bot + "_"
                + (collection == null ? "None" : collection) + SUFFIX + "/points/query");
        return http.executeStrict("POST", url, null, request, "json");
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

    /** type(value).__name__ for JSON-decoded values. */
    private static String pythonType(Object value) {
        if (value instanceof List<?>) {
            return "list";
        }
        if (value instanceof String) {
            return "str";
        }
        if (value instanceof Boolean) {
            return "bool";
        }
        if (value instanceof Double || value instanceof Float || value instanceof java.math.BigDecimal) {
            return "float";
        }
        if (value instanceof Number) {
            return "int";
        }
        return value.getClass().getSimpleName();
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
