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
    public static final String NOT_FOUND = "Cognition schema not found";

    /** SchemaMetadata as Python reads it; absent or null fields take the mongoengine defaults. */
    public record Schema(boolean trainingNeeded, int size, String modelId, String provider) {
        public static final Schema DEFAULT = new Schema(true, 3072, "text-embedding-3-large", "openai");
    }

    /** Effective llm_type plus LLM and embedding secrets after the swap decision. */
    public record Provider(String llmType, Map<String, String> secret, Map<String, String> embeddingSecret) {
    }

    private final ActionCatalog catalog;
    private final LlmSecrets secrets;

    public CognitionSchemas(ActionCatalog catalog, LlmSecrets secrets) {
        this.catalog = catalog;
        this.secrets = secrets;
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

    /** True when {@code collection} is non-default and its schema says no training is needed. */
    public static boolean swapsToOpenrouter(String collection, Schema schema) {
        return collection != null && !collection.isEmpty() && !DEFAULT_COLLECTION.equals(collection)
                && schema != null && !schema.trainingNeeded();
    }

    /**
     * llm_type and secrets for {@code collection}: on a swap both secrets become the openrouter
     * secret; otherwise the llm_type's own secret and its embedding secret (LlmSecrets rules).
     * Callers needing Python's "original secret loaded first" failure order resolve that before.
     */
    public Provider resolveProvider(String bot, String collection, Schema schema, String llmType) {
        if (swapsToOpenrouter(collection, schema)) {
            Map<String, String> secret = secrets.secret(bot, OPENROUTER);
            return new Provider(OPENROUTER, secret, secret);
        }
        return new Provider(llmType, secrets.secret(bot, llmType), secrets.embeddingSecret(bot, llmType));
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
