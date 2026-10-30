package com.kairon.action.catalog;

import org.bson.Document;

import java.util.List;
import java.util.Optional;

public interface ActionCatalog {

    /** mongoengine collection of LLMSecret. */
    String LLM_SECRET = "l_l_m_secret";

    /** mongoengine collection of CognitionSchema. */
    String COGNITION_SCHEMA = "cognition_schema";

    /** mongoengine collection of CollectionData (crud prompt source records). */
    String COGNITION_DATA = "collection_data";

    /** One {@code filterable_attrs} element match {@code {k: key, v: value}}. */
    record AttrFilter(String key, Object value) {
    }

    /**
     * Sysadmin.get_llm_secret lookup: the LLMSecret with {@code {bot, llm_type}}, else the global one
     * ({@code llm_type} with no {@code bot} field). Raw document; decryption is the caller's job.
     */
    Optional<Document> findLlmSecret(String bot, String llmType);

    /**
     * Sysadmin.check_llm_model_exists lookup: the LLMSecret with {@code {bot, llm_type, models contains model}},
     * else the global one with no {@code bot} field.
     */
    Optional<Document> findLlmModel(String bot, String llmType, String model);

    /** CognitionSchema.objects(bot=bot, collection_name=name).first(), name used verbatim. */
    Optional<Document> findCognitionSchema(String bot, String collectionName);

    /**
     * DataProcessor.get_collection_data query: CollectionData of {@code bot} and the lowercased
     * {@code collectionName}, ANDing one {@code filterable_attrs $elemMatch {k, v}} per filter, at most
     * {@code limit} documents. Callers drop falsy pairs before calling.
     */
    List<Document> findCognitionData(String bot, String collectionName, List<AttrFilter> filters, int limit);

    Optional<Document> findActive(String collection, String bot, String nameField, String value);

    List<Document> findAllActive(String collection, String bot, String nameField, String value);

    Optional<Document> findBotSettings(String bot);

    /** mongoengine collection of Integration. */
    String INTEGRATION = "integration";

    /** Integration.objects(bot=bot, status__ne="deleted"). */
    List<Document> findLiveIntegrations(String bot);

    /** AccountProcessor.get_bot: the {@code bot} collection document with {@code _id} {@code id}. */
    Optional<Document> findBotById(String id);

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
