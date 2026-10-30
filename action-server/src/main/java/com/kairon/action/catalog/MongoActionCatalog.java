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
    public List<Document> findLiveIntegrations(String bot) {
        return collection(INTEGRATION).find(Filters.and(Filters.eq("bot", bot), Filters.ne("status", "deleted")))
                .into(new ArrayList<>());
    }

    @Override
    public Optional<Document> findBotById(String id) {
        Object key = ObjectId.isValid(id) ? new ObjectId(id) : id;
        return Optional.ofNullable(collection("bot").find(Filters.eq("_id", key)).first());
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
    public Optional<Document> findLlmSecret(String bot, String llmType) {
        Document found = collection(LLM_SECRET).find(llmSecretQuery(bot, llmType)).first();
        if (found == null) {
            found = collection(LLM_SECRET).find(globalLlmSecretQuery(llmType)).first();
        }
        return Optional.ofNullable(found);
    }

    @Override
    public Optional<Document> findLlmModel(String bot, String llmType, String model) {
        Document found = collection(LLM_SECRET).find(llmModelQuery(bot, llmType, model)).first();
        if (found == null) {
            found = collection(LLM_SECRET).find(globalLlmModelQuery(llmType, model)).first();
        }
        return Optional.ofNullable(found);
    }

    @Override
    public Optional<Document> findCognitionSchema(String bot, String collectionName) {
        return Optional.ofNullable(collection(COGNITION_SCHEMA).find(cognitionSchemaQuery(bot, collectionName)).first());
    }

    @Override
    public List<Document> findCognitionData(String bot, String collectionName, List<AttrFilter> filters, int limit) {
        if (limit <= 0) {
            return new ArrayList<>();
        }
        return collection(COGNITION_DATA).find(cognitionDataQuery(bot, collectionName, filters))
                .limit(limit)
                .into(new ArrayList<>());
    }

    static Bson llmSecretQuery(String bot, String llmType) {
        return Filters.and(Filters.eq("bot", bot), Filters.eq("llm_type", llmType));
    }

    static Bson globalLlmSecretQuery(String llmType) {
        return Filters.and(Filters.eq("llm_type", llmType), Filters.exists("bot", false));
    }

    static Bson llmModelQuery(String bot, String llmType, String model) {
        return Filters.and(Filters.eq("bot", bot), Filters.eq("llm_type", llmType), Filters.in("models", model));
    }

    static Bson globalLlmModelQuery(String llmType, String model) {
        return Filters.and(Filters.eq("llm_type", llmType), Filters.exists("bot", false), Filters.in("models", model));
    }

    static Bson cognitionSchemaQuery(String bot, String collectionName) {
        return Filters.and(Filters.eq("bot", bot), Filters.eq("collection_name", collectionName));
    }

    static Bson cognitionDataQuery(String bot, String collectionName, List<AttrFilter> filters) {
        List<Bson> clauses = new ArrayList<>();
        clauses.add(Filters.eq("bot", bot));
        clauses.add(Filters.eq("collection_name", lower(collectionName)));
        for (AttrFilter filter : filters == null ? List.<AttrFilter>of() : filters) {
            clauses.add(Filters.elemMatch("filterable_attrs",
                    new Document("k", filter.key()).append("v", filter.value())));
        }
        return Filters.and(clauses);
    }

    static String lower(String name) {
        return name == null ? null : name.toLowerCase(java.util.Locale.ROOT);
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
