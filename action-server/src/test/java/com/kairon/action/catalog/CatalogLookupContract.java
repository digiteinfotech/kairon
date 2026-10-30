package com.kairon.action.catalog;

import org.bson.Document;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * T-101: LLM secret / model / cognition schema / cognition data lookups, run against every catalog.
 * llm-vector-clients R6 c1, c4 (lookup half), R7 c1; prompt-database-actions R3 c6 (query half).
 */
abstract class CatalogLookupContract {

    static final String BOT = "bot-a";
    static final String OTHER_BOT = "bot-b";

    abstract ActionCatalog catalog();

    abstract void seed(String collection, Document document);

    private static Document secret(String bot, String llmType, String apiKey, String... models) {
        Document document = new Document("llm_type", llmType).append("api_key", apiKey)
                .append("models", List.of(models)).append("user", "sysadmin");
        if (bot != null) {
            document.append("bot", bot);
        }
        return document;
    }

    private static Document record(String bot, String collection, String marker, Object... pairs) {
        Document data = new Document("marker", marker);
        List<Document> attrs = new java.util.ArrayList<>();
        for (int i = 0; i < pairs.length; i += 2) {
            data.append((String) pairs[i], pairs[i + 1]);
            attrs.add(new Document("k", pairs[i]).append("v", pairs[i + 1]));
        }
        return new Document("bot", bot).append("collection_name", collection).append("data", data)
                .append("is_secure", List.of()).append("is_non_editable", List.of())
                .append("filterable_attrs", attrs).append("user", "u").append("status", true);
    }

    private static List<String> markers(List<Document> documents) {
        return documents.stream().map(d -> d.get("data", Document.class).getString("marker")).sorted().toList();
    }

    // ---- findLlmSecret (R6 c1) ----

    @Test
    void llmSecretPrefersBotDocument() {
        seed(ActionCatalog.LLM_SECRET, secret(null, "openai", "global-key", "gpt-4o"));
        seed(ActionCatalog.LLM_SECRET, secret(BOT, "openai", "bot-key", "gpt-4o"));
        assertEquals("bot-key", catalog().findLlmSecret(BOT, "openai").orElseThrow().getString("api_key"));
    }

    @Test
    void llmSecretFallsBackToGlobalDocumentWithoutBot() {
        seed(ActionCatalog.LLM_SECRET, secret(OTHER_BOT, "openai", "other-bot-key", "gpt-4o"));
        seed(ActionCatalog.LLM_SECRET, secret(null, "openai", "global-key", "gpt-4o"));
        assertEquals("global-key", catalog().findLlmSecret(BOT, "openai").orElseThrow().getString("api_key"));
    }

    @Test
    void llmSecretMissWhenNeitherBotNorGlobal() {
        seed(ActionCatalog.LLM_SECRET, secret(OTHER_BOT, "openai", "other-bot-key", "gpt-4o"));
        seed(ActionCatalog.LLM_SECRET, secret(null, "anthropic", "global-key", "claude"));
        assertTrue(catalog().findLlmSecret(BOT, "openai").isEmpty());
    }

    // ---- findLlmModel (R6 c4, lookup half) ----

    @Test
    void llmModelMatchesBotDocumentContainingModel() {
        seed(ActionCatalog.LLM_SECRET, secret(BOT, "openai", "bot-key", "gpt-4o", "gpt-4o-mini"));
        assertEquals("bot-key", catalog().findLlmModel(BOT, "openai", "gpt-4o-mini").orElseThrow().getString("api_key"));
    }

    @Test
    void llmModelFallsBackToGlobalWhenBotDocumentLacksModel() {
        seed(ActionCatalog.LLM_SECRET, secret(BOT, "openai", "bot-key", "gpt-4o"));
        seed(ActionCatalog.LLM_SECRET, secret(null, "openai", "global-key", "gpt-4.1"));
        assertEquals("global-key", catalog().findLlmModel(BOT, "openai", "gpt-4.1").orElseThrow().getString("api_key"));
    }

    @Test
    void llmModelMissWhenNoDocumentListsModel() {
        seed(ActionCatalog.LLM_SECRET, secret(BOT, "openai", "bot-key", "gpt-4o"));
        seed(ActionCatalog.LLM_SECRET, secret(null, "openai", "global-key", "gpt-4o"));
        seed(ActionCatalog.LLM_SECRET, secret(null, "anthropic", "a-key", "gpt-4.1"));
        assertTrue(catalog().findLlmModel(BOT, "openai", "gpt-4.1").isEmpty());
    }

    // ---- findCognitionSchema (R7 c1) ----

    @Test
    void cognitionSchemaByBotAndVerbatimCollectionName() {
        seed(ActionCatalog.COGNITION_SCHEMA, new Document("bot", BOT).append("collection_name", "Faq_Data")
                .append("schema_metadata", new Document("training_needed", false)));
        seed(ActionCatalog.COGNITION_SCHEMA, new Document("bot", OTHER_BOT).append("collection_name", "products"));
        Optional<Document> hit = catalog().findCognitionSchema(BOT, "Faq_Data");
        assertTrue(hit.isPresent());
        assertEquals("Faq_Data", hit.get().getString("collection_name"));
        assertTrue(catalog().findCognitionSchema(BOT, "faq_data").isEmpty(), "name is not normalised");
        assertTrue(catalog().findCognitionSchema(BOT, "products").isEmpty(), "other bot's schema");
    }

    // ---- findCognitionData (prompt-db R3 c6, query half) ----

    @Test
    void cognitionDataAndsFilterPairsPerElement() {
        seed(ActionCatalog.COGNITION_DATA, record(BOT, "orders", "both", "city", "Pune", "status", "open"));
        seed(ActionCatalog.COGNITION_DATA, record(BOT, "orders", "city-only", "city", "Pune", "status", "closed"));
        seed(ActionCatalog.COGNITION_DATA, record(BOT, "orders", "status-only", "city", "Mumbai", "status", "open"));
        // key and value split across two different elements must not match one $elemMatch
        seed(ActionCatalog.COGNITION_DATA, record(BOT, "orders", "crossed", "city", "open", "status", "Pune"));
        List<Document> found = catalog().findCognitionData(BOT, "orders", List.of(
                new ActionCatalog.AttrFilter("city", "Pune"), new ActionCatalog.AttrFilter("status", "open")), 10);
        assertEquals(List.of("both"), markers(found));
    }

    @Test
    void cognitionDataSingleFilterMatchesNumbersAcrossTypes() {
        seed(ActionCatalog.COGNITION_DATA, record(BOT, "orders", "qty-2", "qty", 2));
        seed(ActionCatalog.COGNITION_DATA, record(BOT, "orders", "qty-3", "qty", 3));
        seed(ActionCatalog.COGNITION_DATA, record(BOT, "orders", "qty-text", "qty", "2"));
        List<Document> found = catalog().findCognitionData(BOT, "orders",
                List.of(new ActionCatalog.AttrFilter("qty", 2.0)), 10);
        assertEquals(List.of("qty-2"), markers(found));
    }

    @Test
    void cognitionDataNoFiltersReturnsBotCollectionOnlyWithinLimit() {
        seed(ActionCatalog.COGNITION_DATA, record(BOT, "orders", "o1", "city", "Pune"));
        seed(ActionCatalog.COGNITION_DATA, record(BOT, "orders", "o2", "city", "Pune"));
        seed(ActionCatalog.COGNITION_DATA, record(BOT, "orders", "o3", "city", "Pune"));
        seed(ActionCatalog.COGNITION_DATA, record(BOT, "users", "u1", "city", "Pune"));
        seed(ActionCatalog.COGNITION_DATA, record(OTHER_BOT, "orders", "b1", "city", "Pune"));
        assertEquals(List.of("o1", "o2", "o3"), markers(catalog().findCognitionData(BOT, "orders", List.of(), 10)));
        assertEquals(2, catalog().findCognitionData(BOT, "orders", List.of(), 2).size());
        assertEquals(1, catalog().findCognitionData(BOT, "orders",
                List.of(new ActionCatalog.AttrFilter("city", "Pune")), 1).size());
    }

    @Test
    void cognitionDataLowercasesCollectionName() {
        seed(ActionCatalog.COGNITION_DATA, record(BOT, "orders", "o1", "city", "Pune"));
        assertEquals(List.of("o1"), markers(catalog().findCognitionData(BOT, "Orders", List.of(), 10)));
    }

    @Test
    void cognitionDataMissReturnsEmpty() {
        seed(ActionCatalog.COGNITION_DATA, record(BOT, "orders", "o1", "city", "Pune"));
        assertFalse(catalog().findCognitionData(BOT, "orders",
                List.of(new ActionCatalog.AttrFilter("city", "Delhi")), 10).iterator().hasNext());
    }
}
