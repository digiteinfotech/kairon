package com.kairon.action.support.llm;

import com.kairon.action.catalog.ActionCatalog;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.runtime.ActionFailure;
import org.bson.Document;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** llm-vector-clients R7: cognition schema lookup, defaults and openrouter swap. */
class CognitionSchemasTest {

    private static final String BOT = "bot-1";

    private final MemoryActionCatalog catalog = new MemoryActionCatalog();
    private final CognitionSchemas schemas = new CognitionSchemas(catalog);

    private void schema(String collection, Document metadata) {
        Document document = new Document("bot", BOT).append("collection_name", collection);
        if (metadata != null) {
            document.append("schema_metadata", metadata);
        }
        catalog.put(ActionCatalog.COGNITION_SCHEMA, document);
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

    /**
     * T-125: CognitionSchema.schema_metadata is EmbeddedDocumentField(SchemaMetadata, default=SchemaMetadata)
     * (kairon/shared/cognition/data_objects.py:50): a doc without (or with null) schema_metadata loads the
     * SchemaMetadata defaults, so prompt.py:89 / database.py:89 read training_needed True and do not fail.
     */
    @Test
    void forActionReadsMissingOrNullSchemaMetadataAsDefaults() {
        schema("absent", null);
        catalog.put(ActionCatalog.COGNITION_SCHEMA, new Document("bot", BOT).append("collection_name", "nulled")
                .append("schema_metadata", null));
        assertEquals(CognitionSchemas.Schema.DEFAULT, schemas.forAction(BOT, "absent"));
        assertEquals(CognitionSchemas.Schema.DEFAULT, schemas.forAction(BOT, "nulled"));
        assertThrows(ActionFailure.class, () -> schemas.forAction(BOT, "missing-doc"));
    }

    @Test
    void promptSwapsOnlyForNonDefaultCollectionWhoseTrainingIsNotNeeded() {
        CognitionSchemas.Schema trained = new CognitionSchemas.Schema(false, 1536, "m", "openrouter");
        assertTrue(CognitionSchemas.swapsToOpenrouter("products", trained));
        assertFalse(CognitionSchemas.swapsToOpenrouter("default", trained));
        assertFalse(CognitionSchemas.swapsToOpenrouter(null, trained));
        assertFalse(CognitionSchemas.swapsToOpenrouter("", trained));
        assertFalse(CognitionSchemas.swapsToOpenrouter("products", CognitionSchemas.Schema.DEFAULT));
        assertFalse(CognitionSchemas.swapsToOpenrouter("products", null));
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
