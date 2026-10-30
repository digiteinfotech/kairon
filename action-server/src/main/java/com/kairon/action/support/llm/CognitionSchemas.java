package com.kairon.action.support.llm;

import com.kairon.action.catalog.ActionCatalog;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;
import org.bson.Document;

import java.util.Map;
import java.util.Optional;

/**
 * CognitionSchema lookup and the openrouter provider swap (kairon/shared/cognition/data_objects.py
 * SchemaMetadata; kairon/actions/definitions/prompt.py and database.py; LLMProcessor.get_embedding).
 */
@Singleton
public class CognitionSchemas {

    /** Collection name that never triggers the provider swap. */
    public static final String DEFAULT_COLLECTION = "default";

    /** Provider used when a collection's embeddings need no training. */
    public static final String OPENROUTER = "openrouter";

    /** Message when an action's collection has no CognitionSchema. */
    /** Python prompt.py:88-89 / database.py:88-89: CognitionSchema.first() is None, then .schema_metadata. */
    public static final String NOT_FOUND = "'NoneType' object has no attribute 'schema_metadata'";

    /** SchemaMetadata as Python reads it; absent or null fields take the mongoengine defaults. */
    public record Schema(boolean trainingNeeded, int size, String modelId, String provider) {
        public static final Schema DEFAULT = new Schema(true, 3072, "text-embedding-3-large", "openai");
    }

    private final ActionCatalog catalog;

    public CognitionSchemas(ActionCatalog catalog) {
        this.catalog = catalog;
    }

    /** CognitionSchema.objects(bot=bot, collection_name=collection).first(), name verbatim. */
    public Optional<Schema> find(String bot, String collection) {
        return catalog.findCognitionSchema(bot, collection).map(CognitionSchemas::read);
    }

    /** LLMProcessor.get_embedding: a missing schema reads as training_needed true (defaults). */
    public Schema forEmbedding(String bot, String collection) {
        return find(bot, collection).orElse(Schema.DEFAULT);
    }

    /** prompt/database actions: a missing schema fails the action. */
    public Schema forAction(String bot, String collection) {
        return find(bot, collection).orElseThrow(() -> new ActionFailure(NOT_FOUND));
    }

    /** database_action (database.py:90): swaps whenever training is not needed, whatever the collection. */
    public static boolean databaseSwapsToOpenrouter(Schema schema) {
        return schema != null && !schema.trainingNeeded();
    }

    /** prompt_action (prompt.py:87): swaps only for a non-default collection whose schema needs no training. */
    public static boolean swapsToOpenrouter(String collection, Schema schema) {
        return collection != null && !collection.isEmpty() && !DEFAULT_COLLECTION.equals(collection)
                && schema != null && !schema.trainingNeeded();
    }

    private static Schema read(Document document) {
        Map<String, Object> metadata = Maps.map(document.get("schema_metadata"));
        Object training = metadata.get("training_needed");
        Object size = metadata.get("size");
        Object modelId = metadata.get("model_id");
        Object provider = metadata.get("provider");
        return new Schema(
                training == null ? Schema.DEFAULT.trainingNeeded() : Maps.truthy(training),
                size instanceof Number number ? number.intValue() : Schema.DEFAULT.size(),
                modelId == null ? Schema.DEFAULT.modelId() : modelId.toString(),
                provider == null ? Schema.DEFAULT.provider() : provider.toString());
    }
}
