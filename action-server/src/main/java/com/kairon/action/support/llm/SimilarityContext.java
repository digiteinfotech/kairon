package com.kairon.action.support.llm;

import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.support.Maps;
import com.kairon.action.support.PyRepr;
import jakarta.inject.Singleton;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * processor.py {@code __attach_similarity_prompt_if_enabled} + {@code _process_similarity_prompt}: every similarity
 * source is searched concurrently with the one query embedding ({@code asyncio.gather}), and each non-empty result is
 * appended to the context as {@code "{context}\n{block}"} in config order.
 */
@Singleton
public class SimilarityContext {

    private final QdrantClient qdrant;

    public SimilarityContext(QdrantClient qdrant) {
        this.qdrant = qdrant;
    }

    /**
     * Searches all sources concurrently on virtual threads (blocking HTTP, as ParallelAction) and appends their
     * blocks in config order. A failing search fails the whole call (gather without return_exceptions); when several
     * fail, the first in config order is raised.
     */
    public String attach(String bot, Object contextPrompt, List<?> similarityPrompts, List<?> vector) {
        String context = PyRepr.str(contextPrompt);
        if (similarityPrompts == null || similarityPrompts.isEmpty()) {
            return context;
        }
        List<CompletableFuture<String>> futures = new ArrayList<>();
        try (ExecutorService pool = Executors.newVirtualThreadPerTaskExecutor()) {
            for (Object source : similarityPrompts) {
                Map<String, Object> config = Maps.map(source);
                futures.add(CompletableFuture.supplyAsync(() -> render(bot, config, vector), pool));
            }
            for (CompletableFuture<String> future : futures) {
                String block = join(future);
                if (block != null && !block.isEmpty()) {
                    context = context + "\n" + block;
                }
            }
        }
        return context;
    }

    /** One source: null when disabled or without hits, else the rendered instructions block. */
    public String render(String bot, Map<String, Object> source, List<?> vector) {
        if (!Maps.truthy(source.get("use_similarity_prompt"))) {
            return null;
        }
        List<Object> values = new ArrayList<>();
        for (Object entry : qdrant.search(bot, source, vector)) {
            values.add(hitValue(entry));
        }
        if (values.isEmpty()) {
            return null;
        }
        return "Instructions on how to use " + PyRepr.str(source.get("similarity_prompt_name")) + ":\n"
                + PyRepr.repr(values) + "\n" + PyRepr.str(source.get("similarity_prompt_instructions")) + "\n";
    }

    /** {@code payload['content']} when present, else the payload without {@code collection_name}. */
    static Object hitValue(Object entry) {
        if (!(entry instanceof Map<?, ?> hit)) {
            throw new ActionFailure("'" + pyType(entry) + "' object has no attribute 'get'");
        }
        Object payload = hit.containsKey("payload") ? hit.get("payload") : Map.of();
        if (!(payload instanceof Map<?, ?> fields)) {
            throw new ActionFailure("argument of type '" + pyType(payload) + "' is not iterable");
        }
        if (fields.containsKey("content")) {
            return fields.get("content");
        }
        Map<Object, Object> rest = new LinkedHashMap<>();
        fields.forEach((key, value) -> {
            if (!"collection_name".equals(key)) {
                rest.put(key, value);
            }
        });
        return rest;
    }

    private static String join(CompletableFuture<String> future) {
        try {
            return future.join();
        } catch (CompletionException e) {
            if (e.getCause() instanceof RuntimeException cause) {
                throw cause;
            }
            throw e;
        }
    }

    private static String pyType(Object value) {
        if (value == null) {
            return "NoneType";
        }
        if (value instanceof String) {
            return "str";
        }
        if (value instanceof Boolean) {
            return "bool";
        }
        if (value instanceof Integer || value instanceof Long || value instanceof java.math.BigInteger) {
            return "int";
        }
        if (value instanceof Number) {
            return "float";
        }
        if (value instanceof List<?>) {
            return "list";
        }
        return value.getClass().getSimpleName();
    }
}
