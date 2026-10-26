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
        bucket(collection).add(deepCopy(document));
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

    @Override
    public Document insert(String collection, Document document) {
        Document copy = deepCopy(document);
        if (copy.get("_id") == null) {
            copy.put("_id", new ObjectId());
        }
        if (copy.get("timestamp") == null) {
            copy.put("timestamp", new Date());
        }
        bucket(collection).add(copy);
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
