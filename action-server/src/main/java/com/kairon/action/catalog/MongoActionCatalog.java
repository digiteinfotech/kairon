package com.kairon.action.catalog;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import io.micronaut.context.annotation.Requires;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.bson.conversions.Bson;
import org.bson.types.ObjectId;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Optional;

@Singleton
@Requires(property = "kairon.action.catalog", value = "mongo")
public class MongoActionCatalog implements ActionCatalog {

    private final MongoDatabase database;

    public MongoActionCatalog(MongoClient client, String databaseName) {
        this.database = client.getDatabase(databaseName);
    }

    @Override
    public Optional<Document> findActive(String collection, String bot, String nameField, String value) {
        Document found = collection(collection).find(active(bot, nameField, value)).first();
        return Optional.ofNullable(found);
    }

    @Override
    public List<Document> findAllActive(String collection, String bot, String nameField, String value) {
        return collection(collection).find(active(bot, nameField, value)).into(new ArrayList<>());
    }

    @Override
    public Optional<Document> findBotSettings(String bot) {
        Document found = collection("bot_settings").find(Filters.and(
                Filters.eq("bot", bot),
                Filters.eq("status", true)
        )).first();
        return Optional.ofNullable(found);
    }

    @Override
    public List<Document> findByBot(String collection, String bot) {
        return collection(collection).find(Filters.eq("bot", bot)).into(new ArrayList<>());
    }

    @Override
    public Document insert(String collection, Document document) {
        if (document.get("_id") == null) {
            document.put("_id", new ObjectId());
        }
        if (document.get("timestamp") == null) {
            document.put("timestamp", new Date());
        }
        collection(collection).insertOne(document);
        return document;
    }

    @Override
    public void replace(String collection, Object id, Document document) {
        document.put("_id", id);
        collection(collection).replaceOne(Filters.eq("_id", id), document);
    }

    @Override
    public List<Document> all(String collection) {
        return collection(collection).find().into(new ArrayList<>());
    }

    private MongoCollection<Document> collection(String name) {
        return database.getCollection(name);
    }

    private static Bson active(String bot, String nameField, String value) {
        return Filters.and(Filters.eq("bot", bot), Filters.eq(nameField, value), Filters.eq("status", true));
    }
}
