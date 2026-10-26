package com.kairon.action.catalog;

import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.BsonDocument;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

/** core-actions R3 c2: the Mongo query mongoengine builds for search_text(..).order_by("$text_score"). */
class MongoTextSearchTest {

    @Test
    void textQueryShape() {
        BsonDocument query = MongoActionCatalog.textQuery("bot-1", "book flight").toBsonDocument();
        assertEquals(BsonDocument.parse(
                "{\"$and\": [{\"bot\": \"bot-1\"}, {\"status\": true}, {\"$text\": {\"$search\": \"book flight\"}}]}"), query);
    }

    @Test
    void scoreProjectionAndSort() {
        assertEquals(BsonDocument.parse("{\"_text_score\": {\"$meta\": \"textScore\"}}"),
                Projections.metaTextScore(MongoActionCatalog.TEXT_SCORE).toBsonDocument());
        assertEquals(BsonDocument.parse("{\"_text_score\": {\"$meta\": \"textScore\"}}"),
                Sorts.metaTextScore(MongoActionCatalog.TEXT_SCORE).toBsonDocument());
    }
}
