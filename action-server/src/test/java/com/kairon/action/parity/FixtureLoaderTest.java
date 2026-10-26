package com.kairon.action.parity;

import org.bson.Document;
import org.bson.types.Binary;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;

import java.net.URISyntaxException;
import java.nio.file.Path;
import java.util.Date;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FixtureLoaderTest {

    static final String MINIMAL = """
            {"schema_version": 1, "node_id": "tests/x.py::test_y", "normalized": false,
             "mongo": {"available": true, "databases": ["db1", "db2"],
               "seed": {"db1": {"actions": [{"_id": {"$oid": "65a1f0c2e4b0a1b2c3d4e5f1"},
                    "when": {"$date": {"$numberLong": "1704067200000"}},
                    "n": {"$numberInt": "7"}, "big": {"$numberLong": "9000000000"}, "f": {"$numberDouble": "1.5"},
                    "raw": {"$binary": {"base64": "AAE=", "subType": "00"}}, "nested": {"list": [{"$numberInt": "1"}]}}]},
                        "db2": {"actions": [{"_id": "plain-id"}]}},
               "written": {"db1": {"logs": {"inserted": [{"_id": {"$oid": "65a1f0c2e4b0a1b2c3d4e5f9"}, "x": 1}],
                                            "updated": [], "deleted": [{"$oid": "65a1f0c2e4b0a1b2c3d4e5f2"}]}},
                           "db2": {"logs": {"inserted": [{"_id": "b"}], "updated": [], "deleted": ["gone"]}}}},
             "exchanges": [{"request": {"method": "POST", "path": "/webhook", "query": "a=1",
                    "headers": [["content-type", "application/json"], ["x-dup", "1"], ["X-Dup", "2"]],
                    "body": {"encoding": "json", "value": {"k": [1, 2]}}},
                  "response": {"status": 200, "headers": [], "body": {"encoding": "text", "value": "ok"}}}],
             "upstream": [
               {"seq": 1, "client": "aiohttp", "request": {"method": "GET", "url": "http://h/b", "headers": [],
                  "body": {"encoding": "empty", "value": null}}, "response": null,
                  "error": {"type": "aiohttp.ClientConnectionError", "message": "boom"}},
               {"seq": 0, "client": "requests", "request": {"method": "POST", "url": "https://h/a", "headers": [],
                  "body": {"encoding": "form", "value": {"a": "1"}}},
                  "response": {"status": 201, "headers": [["Content-Type", "text/plain"]],
                     "body": {"encoding": "base64", "value": "/w=="}}, "error": null}]}
            """;

    @Test
    void loadsTypedModelWithBsonTypesResolved() {
        Fixture fixture = FixtureLoader.parse("minimal", MINIMAL);
        assertEquals(1, fixture.schemaVersion());
        assertEquals("tests/x.py::test_y", fixture.nodeId());
        assertFalse(fixture.normalized());
        assertEquals(List.of("db1", "db2"), fixture.mongo().databases());

        Document seed = fixture.mongo().seed().get("db1").get("actions").get(0);
        assertEquals(new ObjectId("65a1f0c2e4b0a1b2c3d4e5f1"), seed.get("_id"));
        assertEquals(new Date(1704067200000L), seed.get("when"));
        assertEquals(7, seed.get("n"));
        assertEquals(9000000000L, seed.get("big"));
        assertEquals(1.5, seed.get("f"));
        assertInstanceOf(Binary.class, seed.get("raw"));
        assertEquals(List.of(1), ((Document) seed.get("nested")).get("list"));

        // Databases fold into collections for the catalog.
        assertEquals(2, fixture.mongo().seedByCollection().get("actions").size());
        Fixture.Writes logs = fixture.mongo().writtenByCollection().get("logs");
        assertEquals(2, logs.inserted().size());
        assertEquals(List.of(new ObjectId("65a1f0c2e4b0a1b2c3d4e5f2"), "gone"), logs.deleted());

        Fixture.Exchange exchange = fixture.exchanges().get(0);
        assertEquals("a=1", exchange.request().query());
        assertEquals(List.of("1", "2"), Fixture.values(exchange.request().headers(), "X-DUP"));
        assertEquals("json", exchange.request().body().encoding());
        assertEquals(2, exchange.request().body().value().get("k").get(1).intValue());
        assertEquals("ok", exchange.response().body().value().textValue());

        Fixture.UpstreamCall failed = fixture.upstream().get(0);
        assertNull(failed.response());
        assertEquals("aiohttp.ClientConnectionError", failed.error().type());
        Fixture.UpstreamCall ok = fixture.upstream().get(1);
        assertEquals(201, ok.response().status());
        assertEquals("form", ok.request().body().encoding());
    }

    @Test
    void placeholderTokensSurviveDecodingAsStrings() {
        Fixture fixture = FixtureLoader.loadResource(FixtureReplayTest.SLOT_SET);
        Document log = fixture.mongo().writtenByCollection().get("action_server_logs").inserted().get(0);
        assertEquals("{{OBJECT_ID:1}}", log.get("_id"));
        assertEquals("{{TIMESTAMP}}", log.get("timestamp"));
        assertTrue(fixture.normalized());
    }

    @Test
    void refusesUnknownSchemaVersion() {
        FixtureLoader.FixtureException error = assertThrows(FixtureLoader.FixtureException.class,
                () -> FixtureLoader.parse("v2", MINIMAL.replace("\"schema_version\": 1", "\"schema_version\": 2")));
        assertTrue(error.getMessage().contains("unsupported schema_version 2"), error.getMessage());
    }

    @Test
    void refusesStructurallyInvalidFixtures() {
        assertThrows(FixtureLoader.FixtureException.class,
                () -> FixtureLoader.parse("no-node", MINIMAL.replace("\"node_id\": \"tests/x.py::test_y\",", "")));
        assertThrows(FixtureLoader.FixtureException.class,
                () -> FixtureLoader.parse("enc", MINIMAL.replace("\"encoding\": \"text\"", "\"encoding\": \"xml\"")));
        assertThrows(FixtureLoader.FixtureException.class,
                () -> FixtureLoader.parse("empty", MINIMAL.replace("{\"encoding\": \"empty\", \"value\": null}",
                        "{\"encoding\": \"empty\", \"value\": \"x\"}")));
        assertThrows(FixtureLoader.FixtureException.class,
                () -> FixtureLoader.parse("id", MINIMAL.replace("[{\"_id\": \"plain-id\"}]", "[{\"x\": 1}]")));
        assertThrows(FixtureLoader.FixtureException.class,
                () -> FixtureLoader.parse("path", MINIMAL.replace("\"path\": \"/webhook\"", "\"path\": \"webhook\"")));
        assertThrows(FixtureLoader.FixtureException.class,
                () -> FixtureLoader.parse("neither", MINIMAL.replace(
                        "\"error\": {\"type\": \"aiohttp.ClientConnectionError\", \"message\": \"boom\"}", "\"error\": null")));
    }

    @Test
    void loadsEveryBundledFixture() throws URISyntaxException {
        Path dir = Path.of(FixtureLoaderTest.class.getResource("/parity/fixtures").toURI());
        List<Fixture> all = FixtureLoader.loadAll(dir);
        assertEquals(3, all.size());
        assertTrue(all.stream().allMatch(f -> f.nodeId().startsWith("synthetic/")));
    }
}
