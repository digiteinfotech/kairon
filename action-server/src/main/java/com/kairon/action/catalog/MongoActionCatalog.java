package com.kairon.action.catalog;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
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

    /** Field mongoengine projects the text score into. */
    static final String TEXT_SCORE = "_text_score";

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

    /** mongoengine search_text(search).order_by("$text_score").limit(limit) over the {"$text"} index. */
    @Override
    public List<Document> searchText(String collection, String bot, String search, int limit) {
        if (limit <= 0) {
            return new ArrayList<>();
        }
        return collection(collection)
                .find(textQuery(bot, search))
                .projection(Projections.metaTextScore(TEXT_SCORE))
                .sort(Sorts.metaTextScore(TEXT_SCORE))
                .limit(limit)
                .into(new ArrayList<>());
    }

    static Bson textQuery(String bot, String search) {
        return Filters.and(Filters.eq("bot", bot), Filters.eq("status", true), Filters.text(search == null ? "" : search));
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

    @Override
    public Optional<Document> findById(String collection, Object id) {
        if (id == null) {
            return Optional.empty();
        }
        String text = String.valueOf(id);
        Bson filter = ObjectId.isValid(text)
                ? Filters.or(Filters.eq("_id", new ObjectId(text)), Filters.eq("_id", text))
                : Filters.eq("_id", id);
        return Optional.ofNullable(collection(collection).find(filter).first());
    }

    private MongoCollection<Document> collection(String name) {
        return database.getCollection(name);
    }

    private static Bson active(String bot, String nameField, String value) {
        return Filters.and(Filters.eq("bot", bot), Filters.eq(nameField, value), Filters.eq("status", true));
    }
}
