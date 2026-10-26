package com.kairon.action.parity;

import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;

import java.util.Date;
import java.util.List;
import java.util.Map;
import java.util.function.UnaryOperator;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class WrittenDocsTest {

    private static final ObjectId SEEDED = new ObjectId("65a1f0c2e4b0a1b2c3d4e5f1");
    private static final ObjectId REMOVED = new ObjectId("65a1f0c2e4b0a1b2c3d4e5f2");

    private static WrittenDocs.Snapshot snap(String collection, Document... documents) {
        return new WrittenDocs.Snapshot(Map.of(collection, List.of(documents)));
    }

    private static Map<String, Fixture.Writes> recorded(String json) {
        String fixture = """
                {"schema_version": 1, "node_id": "n", "normalized": true,
                 "mongo": {"available": true, "databases": ["d"], "seed": {}, "written": {"d": %s}},
                 "exchanges": [], "upstream": []}
                """.formatted(json);
        return FixtureLoader.parse("written", fixture).mongo().writtenByCollection();
    }

    private static List<String> diff(Map<String, Fixture.Writes> expected, Map<String, Fixture.Writes> actual) {
        return WrittenDocs.diff(expected, actual, new JsonMatcher(new Placeholders.Bindings()), UnaryOperator.identity());
    }

    @Test
    void derivesInsertedUpdatedAndDeletedFromSnapshots() {
        WrittenDocs.Snapshot before = snap("c", new Document("_id", SEEDED).append("v", 1), new Document("_id", REMOVED));
        Document fresh = new Document("_id", new ObjectId()).append("v", 9);
        WrittenDocs.Snapshot after = snap("c", new Document("_id", SEEDED).append("v", 2), fresh);
        Fixture.Writes writes = WrittenDocs.actualWrites(before, after).get("c");
        assertEquals(List.of(fresh), writes.inserted());
        assertEquals(2, writes.updated().get(0).get("v"));
        assertEquals(List.of(REMOVED), writes.deleted());
        assertTrue(WrittenDocs.actualWrites(before, before).isEmpty());
    }

    @Test
    void matchesIgnoringIdAndTimestampFieldsInAnyOrder() {
        Map<String, Fixture.Writes> expected = recorded("""
                {"logs": {"inserted": [
                   {"_id": "{{OBJECT_ID:1}}", "action": "b", "timestamp": "{{TIMESTAMP}}", "n": {"$numberInt": "2"}},
                   {"_id": {"$oid": "65a1f0c2e4b0a1b2c3d4e5aa"}, "action": "a", "timestamp": {"$date": {"$numberLong": "1"}},
                    "created_on": {"$date": {"$numberLong": "1"}}, "meta": {"when": {"$date": {"$numberLong": "1"}}}}],
                  "updated": [], "deleted": [{"$oid": "65a1f0c2e4b0a1b2c3d4e5f2"}]}}
                """);
        Map<String, Fixture.Writes> actual = Map.of("logs", new Fixture.Writes(List.of(
                new Document("_id", new ObjectId()).append("action", "a").append("timestamp", new Date())
                        .append("created_on", new Date()).append("meta", new Document("when", new Date())),
                new Document("_id", "x").append("action", "b").append("n", 2L).append("timestamp", new Date())),
                List.of(), List.of(REMOVED)));
        List<String> problems = diff(expected, actual);
        assertTrue(problems.isEmpty(), String.join("\n", problems));
    }

    @Test
    void reportsFieldDifferencesMissingAndUnexpectedWrites() {
        Map<String, Fixture.Writes> expected = recorded("""
                {"logs": {"inserted": [{"_id": "{{OBJECT_ID:1}}", "status": "Success", "request_id": "{{REQUEST_ID}}"}],
                          "updated": [], "deleted": []}}
                """);
        Map<String, Fixture.Writes> actual = Map.of(
                "logs", new Fixture.Writes(List.of(new Document("_id", new ObjectId()).append("status", "Failure")
                        .append("request_id", "r1")), List.of(), List.of()),
                "callback_data", new Fixture.Writes(List.of(new Document("_id", new ObjectId()).append("x", 1)), List.of(), List.of()));
        List<String> problems = diff(expected, actual);
        String all = String.join("\n", problems);
        assertTrue(all.contains("logs.inserted: $.status: expected \"Success\" but was \"Failure\""), all);
        assertTrue(all.contains("callback_data.inserted: unexpected document written"), all);

        List<String> missing = diff(expected, Map.of());
        assertEquals(1, missing.size(), missing.toString());
        assertTrue(missing.get(0).startsWith("logs.inserted: recorded document not written"), missing.toString());
    }

    @Test
    void appliesOutputRewriteToActualDocuments() {
        Map<String, Fixture.Writes> expected = recorded("""
                {"logs": {"inserted": [{"_id": "{{OBJECT_ID:1}}", "url": "http://localhost:8081/orders"}], "updated": [], "deleted": []}}
                """);
        Map<String, Fixture.Writes> actual = Map.of("logs", new Fixture.Writes(
                List.of(new Document("_id", new ObjectId()).append("url", "http://127.0.0.1:5555/orders")), List.of(), List.of()));
        List<String> problems = WrittenDocs.diff(expected, actual, new JsonMatcher(new Placeholders.Bindings()),
                text -> text.replace("http://127.0.0.1:5555", "http://localhost:8081"));
        assertTrue(problems.isEmpty(), String.join("\n", problems));
    }
}
