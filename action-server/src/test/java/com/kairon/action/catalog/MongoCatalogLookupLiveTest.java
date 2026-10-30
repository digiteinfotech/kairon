package com.kairon.action.catalog;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;

import static org.junit.jupiter.api.Assumptions.assumeTrue;

/** T-101 seeded lookup contract against a live Mongo; skipped unless {@code KAIRON_TEST_MONGO_URI} is set. */
class MongoCatalogLookupLiveTest extends CatalogLookupContract {

    private static MongoClient client;
    private static final String DB = "kairon_t101_lookup_test";

    @BeforeAll
    static void connect() {
        String uri = System.getenv("KAIRON_TEST_MONGO_URI");
        assumeTrue(uri != null && !uri.isBlank(), "KAIRON_TEST_MONGO_URI not set");
        client = MongoClients.create(uri);
    }

    @AfterAll
    static void close() {
        if (client != null) {
            client.getDatabase(DB).drop();
            client.close();
        }
    }

    @BeforeEach
    void reset() {
        client.getDatabase(DB).drop();
    }

    @Override
    ActionCatalog catalog() {
        return new MongoActionCatalog(client, DB);
    }

    @Override
    void seed(String collection, Document document) {
        client.getDatabase(DB).getCollection(collection).insertOne(document);
    }
}
