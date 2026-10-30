package com.kairon.action.support.llm;

import com.kairon.action.ActionSettings;
import com.kairon.action.catalog.ActionCatalog;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.support.Tokens;
import org.bson.Document;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** llm-vector-clients R7: cognition schema lookup, defaults and openrouter swap. */
class CognitionSchemasTest {

    private static final String FERNET = "WvNf7igjO89j9xdRtVMrW7bvVy67uV3ZM9yjwDHkC7E=";
    private static final String BOT = "bot-1";

    private final MemoryActionCatalog catalog = new MemoryActionCatalog();
    private final Tokens tokens = tokens();
    private final CognitionSchemas schemas = new CognitionSchemas(catalog, new LlmSecrets(catalog, tokens));

    private static Tokens tokens() {
        ActionSettings settings = new ActionSettings();
        settings.setFernetKey(FERNET);
        return new Tokens(settings);
    }

    private void schema(String collection, Document metadata) {
        Document document = new Document("bot", BOT).append("collection_name", collection);
        if (metadata != null) {
            document.append("schema_metadata", metadata);
        }
        catalog.put(ActionCatalog.COGNITION_SCHEMA, document);
    }

    private void secret(String llmType, String apiKey) {
        catalog.put(ActionCatalog.LLM_SECRET, new Document("bot", BOT)
                .append("llm_type", llmType).append("api_key", tokens.encrypt(apiKey)));
    }

    @Test
    void lookupUsesBotAndCollectionNameVerbatim() {
        schema("Products", new Document("training_needed", false).append("size", 1536)
                .append("model_id", "m-1").append("provider", "p-1"));
        schema("products", new Document("training_needed", true));
        catalog.put(ActionCatalog.COGNITION_SCHEMA, new Document("bot", "other")
                .append("collection_name", "Products").append("schema_metadata", new Document("training_needed", true)));

        CognitionSchemas.Schema found = schemas.find(BOT, "Products").orElseThrow();
        assertEquals(new CognitionSchemas.Schema(false, 1536, "m-1", "p-1"), found);
        assertTrue(schemas.find(BOT, "products").orElseThrow().trainingNeeded());
        assertTrue(schemas.find(BOT, "PRODUCTS").isEmpty());
        assertTrue(schemas.find("bot-2", "Products").isEmpty());
    }

    @Test
    void emptyOrMissingMetadataReadsAsDefaults() {
        schema("absent", null);
        schema("empty", new Document());
        schema("nulls", new Document("training_needed", null).append("size", null).append("model_id", null));
        for (String collection : new String[] {"absent", "empty", "nulls"}) {
            CognitionSchemas.Schema found = schemas.find(BOT, collection).orElseThrow();
            assertTrue(found.trainingNeeded(), collection);
            assertEquals(3072, found.size(), collection);
            assertEquals("text-embedding-3-large", found.modelId(), collection);
            assertEquals("openai", found.provider(), collection);
        }
        assertEquals(CognitionSchemas.Schema.DEFAULT, schemas.find(BOT, "empty").orElseThrow());
    }

    @Test
    void partialMetadataKeepsDefaultsForMissingFields() {
        schema("partial", new Document("training_needed", false));
        CognitionSchemas.Schema found = schemas.find(BOT, "partial").orElseThrow();
        assertFalse(found.trainingNeeded());
        assertEquals(3072, found.size());
        assertEquals("text-embedding-3-large", found.modelId());
    }

    @Test
    void forEmbeddingTreatsMissingSchemaAsTrainingNeeded() {
        CognitionSchemas.Schema found = schemas.forEmbedding(BOT, "missing");
        assertTrue(found.trainingNeeded());
        assertEquals(CognitionSchemas.Schema.DEFAULT, found);
        schema("present", new Document("training_needed", false));
        assertFalse(schemas.forEmbedding(BOT, "present").trainingNeeded());
    }

    @Test
    void forActionFailsOnMissingSchema() {
        ActionFailure failure = assertThrows(ActionFailure.class, () -> schemas.forAction(BOT, "missing"));
        assertEquals(CognitionSchemas.NOT_FOUND, failure.getMessage());
        assertEquals("'NoneType' object has no attribute 'schema_metadata'", failure.getMessage());
        schema("present", new Document("training_needed", false));
        assertFalse(schemas.forAction(BOT, "present").trainingNeeded());
    }

    @Test
    void swapsToOpenrouterWhenNotDefaultAndTrainingNotNeeded() {
        secret("openai", "openai-key");
        secret("anthropic", "anthropic-key");
        secret("openrouter", "router-key");
        CognitionSchemas.Schema trained = new CognitionSchemas.Schema(false, 1536, "m", "openrouter");

        CognitionSchemas.Provider provider = schemas.resolveProvider(BOT, "products", trained, "anthropic");
        assertEquals("openrouter", provider.llmType());
        assertEquals(Map.of("api_key", "router-key"), provider.secret());
        assertEquals(Map.of("api_key", "router-key"), provider.embeddingSecret());
    }

    @Test
    void keepsLlmTypeWhenDefaultCollectionOrTrainingNeededOrNoCollection() {
        secret("openai", "openai-key");
        secret("anthropic", "anthropic-key");
        secret("openrouter", "router-key");
        CognitionSchemas.Schema trained = new CognitionSchemas.Schema(false, 1536, "m", "openrouter");

        for (CognitionSchemas.Provider provider : new CognitionSchemas.Provider[] {
                schemas.resolveProvider(BOT, "default", trained, "anthropic"),
                schemas.resolveProvider(BOT, "products", CognitionSchemas.Schema.DEFAULT, "anthropic"),
                schemas.resolveProvider(BOT, null, trained, "anthropic"),
                schemas.resolveProvider(BOT, "products", null, "anthropic")}) {
            assertEquals("anthropic", provider.llmType());
            assertEquals(Map.of("api_key", "anthropic-key"), provider.secret());
            assertEquals(Map.of("api_key", "openai-key"), provider.embeddingSecret());
        }
    }

    @Test
    void openrouterLlmTypeStaysOpenrouterWithOwnSecrets() {
        secret("openrouter", "router-key");
        CognitionSchemas.Provider provider = schemas.resolveProvider(
                BOT, "products", new CognitionSchemas.Schema(false, 1536, "m", "openrouter"), "openrouter");
        assertEquals("openrouter", provider.llmType());
        assertEquals(Map.of("api_key", "router-key"), provider.secret());
        assertEquals(Map.of("api_key", "router-key"), provider.embeddingSecret());
    }

    @Test
    void swapFailsWhenOpenrouterSecretMissing() {
        secret("openai", "openai-key");
        ActionFailure failure = assertThrows(ActionFailure.class, () -> schemas.resolveProvider(
                BOT, "products", new CognitionSchemas.Schema(false, 1536, "m", "openrouter"), "openai"));
        assertEquals("LLM secret for 'openrouter' is not configured!", failure.getMessage());
    }

    @Test
    void databaseSwapsWheneverTrainingNotNeededEvenForDefaultCollection() {
        CognitionSchemas.Schema trained = new CognitionSchemas.Schema(false, 3072, "m", "openai");
        assertTrue(CognitionSchemas.databaseSwapsToOpenrouter(trained));
        assertTrue(!CognitionSchemas.swapsToOpenrouter("default", trained));
        assertTrue(!CognitionSchemas.databaseSwapsToOpenrouter(CognitionSchemas.Schema.DEFAULT));
        assertTrue(!CognitionSchemas.databaseSwapsToOpenrouter(null));
    }
}
