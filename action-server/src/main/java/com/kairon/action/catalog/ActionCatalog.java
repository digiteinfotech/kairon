package com.kairon.action.catalog;

import org.bson.Document;

import java.util.List;
import java.util.Optional;

public interface ActionCatalog {

    Optional<Document> findActive(String collection, String bot, String nameField, String value);

    List<Document> findAllActive(String collection, String bot, String nameField, String value);

    Optional<Document> findBotSettings(String bot);

    List<Document> findByBot(String collection, String bot);

    /**
     * MongoProcessor.search_training_examples: documents of {@code collection} with {@code bot} and
     * {@code status: true} matching a {@code $text} search for {@code search}, ordered by text score
     * (best first) and limited to {@code limit}.
     */
    List<Document> searchText(String collection, String bot, String search, int limit);

    Document insert(String collection, Document document);

    void replace(String collection, Object id, Document document);

    List<Document> all(String collection);

    /**
     * The document of {@code collection} whose {@code _id} is {@code id} (mongoengine objects(id=...)):
     * an ObjectId-shaped id matches either the ObjectId or the plain string.
     */
    default Optional<Document> findById(String collection, Object id) {
        if (id == null) {
            return Optional.empty();
        }
        String wanted = String.valueOf(id);
        for (Document document : all(collection)) {
            Object key = document.get("_id");
            if (key != null && wanted.equals(String.valueOf(key))) {
                return Optional.of(document);
            }
        }
        return Optional.empty();
    }
}
