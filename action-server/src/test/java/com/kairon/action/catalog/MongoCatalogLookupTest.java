package com.kairon.action.catalog;

import org.bson.BsonDocument;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * T-101 against MongoActionCatalog: the exact query shapes (always run);
 * the seeded contract runs in MongoCatalogLookupLiveTest.
 */
class MongoCatalogLookupTest {

    @Test
    void llmSecretQueries() {
        assertEquals(BsonDocument.parse("{\"$and\": [{\"bot\": \"b\"}, {\"llm_type\": \"openai\"}]}"),
                MongoActionCatalog.llmSecretQuery("b", "openai").toBsonDocument());
        assertEquals(BsonDocument.parse("{\"$and\": [{\"llm_type\": \"openai\"}, {\"bot\": {\"$exists\": false}}]}"),
                MongoActionCatalog.globalLlmSecretQuery("openai").toBsonDocument());
    }

    @Test
    void llmModelQueries() {
        assertEquals(BsonDocument.parse(
                        "{\"$and\": [{\"bot\": \"b\"}, {\"llm_type\": \"openai\"}, {\"models\": {\"$in\": [\"gpt-4o\"]}}]}"),
                MongoActionCatalog.llmModelQuery("b", "openai", "gpt-4o").toBsonDocument());
        assertEquals(BsonDocument.parse(
                        "{\"$and\": [{\"llm_type\": \"openai\"}, {\"bot\": {\"$exists\": false}}, {\"models\": {\"$in\": [\"gpt-4o\"]}}]}"),
                MongoActionCatalog.globalLlmModelQuery("openai", "gpt-4o").toBsonDocument());
    }

    @Test
    void cognitionSchemaQueryKeepsNameVerbatim() {
        assertEquals(BsonDocument.parse("{\"$and\": [{\"bot\": \"b\"}, {\"collection_name\": \"Faq_Data\"}]}"),
                MongoActionCatalog.cognitionSchemaQuery("b", "Faq_Data").toBsonDocument());
    }

    @Test
    void cognitionDataQueryOneElemMatchPerPair() {
        assertEquals(BsonDocument.parse("{\"$and\": [{\"bot\": \"b\"}, {\"collection_name\": \"orders\"},"
                        + " {\"filterable_attrs\": {\"$elemMatch\": {\"k\": \"city\", \"v\": \"Pune\"}}},"
                        + " {\"filterable_attrs\": {\"$elemMatch\": {\"k\": \"qty\", \"v\": 2}}}]}"),
                MongoActionCatalog.cognitionDataQuery("b", "Orders", List.of(
                        new ActionCatalog.AttrFilter("city", "Pune"), new ActionCatalog.AttrFilter("qty", 2))).toBsonDocument());
        assertEquals(BsonDocument.parse("{\"$and\": [{\"bot\": \"b\"}, {\"collection_name\": \"orders\"}]}"),
                MongoActionCatalog.cognitionDataQuery("b", "orders", List.of()).toBsonDocument());
    }
}
