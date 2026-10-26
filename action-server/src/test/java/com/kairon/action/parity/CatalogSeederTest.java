package com.kairon.action.parity;

import com.kairon.action.catalog.MemoryActionCatalog;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;

import java.util.Date;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CatalogSeederTest {

    @Test
    void seedsEveryDocumentIntoTheCatalogWithBsonTypes() {
        MemoryActionCatalog catalog = new MemoryActionCatalog();
        Fixture fixture = FixtureLoader.loadResource(FixtureReplayTest.SLOT_SET);
        assertEquals(2, CatalogSeeder.seed(fixture, catalog::put));
        Document action = catalog.findActive("actions", "5f50fd0a56b698ca10d35d2e", "name", "set_location").orElseThrow();
        assertEquals(new ObjectId("65a1f0c2e4b0a1b2c3d4e5f1"), action.get("_id"));
        assertEquals(new Date(1704067200000L), action.get("timestamp"));
        assertEquals("slot_set_action", action.get("type"));
        Document config = catalog.findActive("slot_set_action", "5f50fd0a56b698ca10d35d2e", "name", "set_location").orElseThrow();
        assertEquals(2, ((List<?>) config.get("set_slots")).size());
    }

    @Test
    void rewritesRecordedOriginsAtAnyDepth() {
        MemoryActionCatalog catalog = new MemoryActionCatalog();
        Fixture fixture = FixtureLoader.loadResource(FixtureReplayTest.HTTP_POST);
        CatalogSeeder.seed(fixture, catalog::put, text -> text.replace("http://localhost:8081", "http://127.0.0.1:1"));
        Document config = catalog.all("http_action_config").get(0);
        assertEquals("http://127.0.0.1:1/orders", config.get("http_url"));
        Document header = (Document) ((List<?>) config.get("headers")).get(0);
        assertEquals("Bearer order-token", header.get("value"));
        assertTrue(config.get("_id") instanceof ObjectId);
    }
}
