package com.kairon.action.catalog;

import org.bson.Document;

import java.util.List;
import java.util.Optional;

public interface ActionCatalog {

    Optional<Document> findActive(String collection, String bot, String nameField, String value);

    List<Document> findAllActive(String collection, String bot, String nameField, String value);

    Optional<Document> findBotSettings(String bot);

    List<Document> findByBot(String collection, String bot);

    Document insert(String collection, Document document);

    void replace(String collection, Object id, Document document);

    List<Document> all(String collection);
}
