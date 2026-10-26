package com.kairon.action.catalog;

import io.micronaut.context.annotation.Requires;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.bson.types.ObjectId;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

@Singleton
@Requires(property = "kairon.action.catalog", value = "memory")
public class MemoryActionCatalog implements ActionCatalog {

    private final ConcurrentHashMap<String, List<Document>> data = new ConcurrentHashMap<>();

    public void put(String collection, Document document) {
        add(collection, deepCopy(document));
    }

    public void clear() {
        data.clear();
    }

    @Override
    public Optional<Document> findActive(String collection, String bot, String nameField, String value) {
        return findAllActive(collection, bot, nameField, value).stream().findFirst();
    }

    @Override
    public List<Document> findAllActive(String collection, String bot, String nameField, String value) {
        List<Document> matches = new ArrayList<>();
        for (Document document : snapshot(collection)) {
            if (bot.equals(str(document.get("bot")))
                    && value.equals(str(document.get(nameField)))
                    && truthyStatus(document.get("status"))) {
                matches.add(deepCopy(document));
            }
        }
        return matches;
    }

    @Override
    public Optional<Document> findBotSettings(String bot) {
        for (Document document : snapshot("bot_settings")) {
            if (bot.equals(str(document.get("bot"))) && truthyStatus(document.get("status"))) {
                return Optional.of(deepCopy(document));
            }
        }
        return Optional.empty();
    }

    @Override
    public List<Document> findByBot(String collection, String bot) {
        List<Document> matches = new ArrayList<>();
        for (Document document : snapshot(collection)) {
            if (bot.equals(str(document.get("bot")))) {
                matches.add(deepCopy(document));
            }
        }
        return matches;
    }

    /**
     * In-memory stand-in for the Mongo {@code $text} search (indexed field: {@code text}).
     * Approximation: lowercase tokens split on non-letter/digit characters, a small English stop-word list,
     * crude suffix stemming (ing/ed/es/s) instead of Snowball, {@code -term} negation, no phrase matching and
     * no diacritic folding. Score is the number of query-term occurrences in the text divided by the text's
     * token count (Mongo also favours dense matches); ties keep insertion order. Only documents with at least
     * one matching term are returned, best first, limited to {@code limit}.
     */
    @Override
    public List<Document> searchText(String collection, String bot, String search, int limit) {
        List<String> wanted = new ArrayList<>();
        List<String> negated = new ArrayList<>();
        for (String raw : search == null ? new String[0] : search.trim().split("\\s+")) {
            boolean negate = raw.startsWith("-") && raw.length() > 1;
            for (String term : terms(negate ? raw.substring(1) : raw)) {
                (negate ? negated : wanted).add(term);
            }
        }
        if (limit <= 0 || wanted.isEmpty()) {
            return new ArrayList<>();
        }
        record Scored(Document document, double score, int order) {}
        List<Scored> scored = new ArrayList<>();
        int order = 0;
        for (Document document : snapshot(collection)) {
            order++;
            if (!bot.equals(str(document.get("bot"))) || !truthyStatus(document.get("status"))) {
                continue;
            }
            List<String> tokens = terms(str(document.get("text")));
            if (tokens.isEmpty() || negated.stream().anyMatch(tokens::contains)) {
                continue;
            }
            int hits = 0;
            for (String term : new java.util.LinkedHashSet<>(wanted)) {
                for (String token : tokens) {
                    if (token.equals(term)) {
                        hits++;
                    }
                }
            }
            if (hits > 0) {
                scored.add(new Scored(document, hits / (double) tokens.size(), order));
            }
        }
        scored.sort(java.util.Comparator.comparingDouble(Scored::score).reversed().thenComparingInt(Scored::order));
        List<Document> out = new ArrayList<>();
        for (Scored item : scored.subList(0, Math.min(limit, scored.size()))) {
            Document copy = deepCopy(item.document());
            copy.put("_text_score", item.score());
            out.add(copy);
        }
        return out;
    }

    private static final java.util.Set<String> STOP_WORDS = java.util.Set.of(
            "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "if", "in", "into", "is", "it",
            "no", "not", "of", "on", "or", "such", "that", "the", "their", "then", "there", "these", "they",
            "this", "to", "was", "will", "with", "i", "me", "my", "we", "you", "your", "do", "does", "what", "how");

    static List<String> terms(String text) {
        List<String> out = new ArrayList<>();
        if (text == null) {
            return out;
        }
        for (String word : text.toLowerCase(java.util.Locale.ROOT).split("[^\\p{L}\\p{N}]+")) {
            if (word.isEmpty() || STOP_WORDS.contains(word)) {
                continue;
            }
            out.add(stem(word));
        }
        return out;
    }

    private static String stem(String word) {
        for (String suffix : new String[]{"ing", "ed", "es", "s"}) {
            if (word.endsWith(suffix) && word.length() - suffix.length() >= 3 && !word.endsWith("ss")) {
                return word.substring(0, word.length() - suffix.length());
            }
        }
        return word;
    }

    @Override
    public Document insert(String collection, Document document) {
        Document copy = deepCopy(document);
        if (copy.get("_id") == null) {
            copy.put("_id", new ObjectId());
        }
        if (copy.get("timestamp") == null) {
            copy.put("timestamp", new Date());
        }
        add(collection, copy);
        return deepCopy(copy);
    }

    @Override
    public void replace(String collection, Object id, Document document) {
        List<Document> list = bucket(collection);
        synchronized (list) {
            for (int i = 0; i < list.size(); i++) {
                if (id.equals(list.get(i).get("_id"))) {
                    Document copy = deepCopy(document);
                    copy.put("_id", id);
                    list.set(i, copy);
                    return;
                }
            }
            list.add(deepCopy(document));
        }
    }

    @Override
    public List<Document> all(String collection) {
        List<Document> copy = new ArrayList<>();
        for (Document document : snapshot(collection)) {
            copy.add(deepCopy(document));
        }
        return copy;
    }

    /** Children of a parallel_action write logs concurrently; the bucket is a plain ArrayList. */
    private void add(String collection, Document document) {
        List<Document> list = bucket(collection);
        synchronized (list) {
            list.add(document);
        }
    }

    private List<Document> bucket(String collection) {
        return data.computeIfAbsent(collection, key -> new ArrayList<>());
    }

    private List<Document> snapshot(String collection) {
        List<Document> list = data.get(collection);
        if (list == null) {
            return List.of();
        }
        synchronized (list) {
            return new ArrayList<>(list);
        }
    }

    static boolean truthyStatus(Object status) {
        if (status instanceof Boolean flag) {
            return flag;
        }
        return "true".equalsIgnoreCase(String.valueOf(status));
    }

    private static String str(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    @SuppressWarnings("unchecked")
    static Document deepCopy(Document document) {
        return new Document((java.util.Map<String, Object>) deep(document));
    }

    private static Object deep(Object value) {
        if (value instanceof Document document) {
            Document copy = new Document();
            document.forEach((key, item) -> copy.put(key, deep(item)));
            return copy;
        }
        if (value instanceof java.util.Map<?, ?> map) {
            Document copy = new Document();
            map.forEach((key, item) -> copy.put(String.valueOf(key), deep(item)));
            return copy;
        }
        if (value instanceof List<?> list) {
            List<Object> copy = new ArrayList<>();
            for (Object item : list) {
                copy.add(deep(item));
            }
            return copy;
        }
        return value;
    }
}
