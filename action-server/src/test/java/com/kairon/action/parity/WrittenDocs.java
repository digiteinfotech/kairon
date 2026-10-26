package com.kairon.action.parity;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.bson.Document;
import org.bson.json.JsonMode;
import org.bson.json.JsonWriterSettings;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.function.UnaryOperator;

/**
 * Diff of documents written during a replay against the fixture's {@code mongo.written}. The actual writes are
 * derived from two catalog snapshots (after seeding, after the replay): inserted = new {@code _id}s, updated =
 * same {@code _id} with different content, deleted = {@code _id}s that disappeared.
 * <p>
 * Inserted and updated documents are matched as multisets (insertion order is not asserted), ignoring
 * {@code _id} and the timestamp-type fields listed in fixture-schema.md, and treating any two BSON dates as equal.
 * Every other field, including {@code request_id}, is compared with placeholder awareness through the shared
 * bindings, except the run-time measurements of {@link JsonMatcher#ignoringVolatile()}: {@code time_elapsed} numbers
 * at any depth (the http_action log and its {@code events[]} sub-documents) and {@code response_headers.date}.
 */
final class WrittenDocs {

    /** Top-level fields never compared: the id and the volatile timestamp fields of fixture-schema.md. */
    static final Set<String> IGNORED = Set.of("_id", "timestamp", "start_timestamp", "end_timestamp", "created_on",
            "updated_on", "user_timestamp", "next_run_time");

    /** Collections the port writes to; watched for unexpected writes even when the fixture recorded none. */
    static final Set<String> WATCHED = Set.of("action_server_logs", "callback_data", "callback_config", "channel_logs",
            "executor_logs");

    private static final JsonWriterSettings CANONICAL = JsonWriterSettings.builder().outputMode(JsonMode.EXTENDED).build();

    private WrittenDocs() {
    }

    /** Collection name to its documents at one moment. */
    record Snapshot(Map<String, List<Document>> collections) {
        List<Document> get(String name) {
            return collections.getOrDefault(name, List.of());
        }
    }

    /** Collections worth snapshotting for {@code fixture}: seeded, recorded as written, and {@link #WATCHED}. */
    static Set<String> collections(Fixture fixture) {
        Set<String> out = new LinkedHashSet<>(fixture.mongo().seedByCollection().keySet());
        out.addAll(fixture.mongo().writtenByCollection().keySet());
        out.addAll(WATCHED);
        return out;
    }

    static Snapshot snapshot(Function<String, List<Document>> reader, Collection<String> names) {
        Map<String, List<Document>> out = new LinkedHashMap<>();
        for (String name : names) {
            out.put(name, List.copyOf(reader.apply(name)));
        }
        return new Snapshot(out);
    }

    /** The writes between two snapshots, per collection (collections without changes are omitted). */
    static Map<String, Fixture.Writes> actualWrites(Snapshot before, Snapshot after) {
        Set<String> names = new LinkedHashSet<>(before.collections().keySet());
        names.addAll(after.collections().keySet());
        Map<String, Fixture.Writes> out = new LinkedHashMap<>();
        for (String name : names) {
            Map<String, Document> old = byId(before.get(name));
            Map<String, Document> now = byId(after.get(name));
            List<Document> inserted = new ArrayList<>();
            List<Document> updated = new ArrayList<>();
            List<Object> deleted = new ArrayList<>();
            now.forEach((id, document) -> {
                Document previous = old.get(id);
                if (previous == null) {
                    inserted.add(document);
                } else if (!canonical(previous).equals(canonical(document))) {
                    updated.add(document);
                }
            });
            old.forEach((id, document) -> {
                if (!now.containsKey(id)) {
                    deleted.add(document.get("_id"));
                }
            });
            Fixture.Writes writes = new Fixture.Writes(inserted, updated, deleted);
            if (!writes.isEmpty()) {
                out.put(name, writes);
            }
        }
        return out;
    }

    /**
     * Mismatches between the recorded writes and the actual ones. {@code rewrite} is applied to every string of the
     * actual documents first (stub origins back to recorded origins).
     */
    static List<String> diff(Map<String, Fixture.Writes> expected, Map<String, Fixture.Writes> actual,
                             JsonMatcher matcher, UnaryOperator<String> rewrite) {
        JsonMatcher docs = matcher.ignoringTopLevel(IGNORED).ignoringDates().ignoringVolatile();
        List<String> out = new ArrayList<>();
        Set<String> names = new LinkedHashSet<>(expected.keySet());
        names.addAll(actual.keySet());
        for (String name : names) {
            Fixture.Writes want = expected.getOrDefault(name, Fixture.Writes.NONE);
            Fixture.Writes got = actual.getOrDefault(name, Fixture.Writes.NONE);
            matchAll(name + ".inserted", toJson(want.inserted(), UnaryOperator.identity()), toJson(got.inserted(), rewrite), docs, out);
            matchAll(name + ".updated", toJson(want.updated(), UnaryOperator.identity()), toJson(got.updated(), rewrite), docs, out);
            matchAll(name + ".deleted", ids(want.deleted()), ids(got.deleted()), matcher, out);
        }
        return out;
    }

    private static void matchAll(String label, List<JsonNode> expected, List<JsonNode> actual, JsonMatcher matcher, List<String> out) {
        List<JsonNode> remaining = new ArrayList<>(actual);
        List<JsonNode> unmatched = new ArrayList<>();
        for (JsonNode want : expected) {
            int found = -1;
            for (int i = 0; i < remaining.size() && found < 0; i++) {
                if (matcher.matches(want, remaining.get(i))) {
                    found = i;
                }
            }
            if (found >= 0) {
                remaining.remove(found);
            } else {
                unmatched.add(want);
            }
        }
        if (unmatched.isEmpty() && remaining.isEmpty()) {
            return;
        }
        if (unmatched.size() == 1 && remaining.size() == 1) {
            for (String problem : matcher.compare(unmatched.get(0), remaining.get(0))) {
                out.add(label + ": " + problem);
            }
            return;
        }
        for (JsonNode want : unmatched) {
            out.add(label + ": recorded document not written: " + want);
        }
        for (JsonNode got : remaining) {
            out.add(label + ": unexpected document written: " + got);
        }
    }

    private static List<JsonNode> toJson(List<Document> documents, UnaryOperator<String> rewrite) {
        List<JsonNode> out = new ArrayList<>();
        for (Document document : documents) {
            out.add(json((Document) CatalogSeeder.rewrite(document, rewrite)));
        }
        return out;
    }

    private static List<JsonNode> ids(List<Object> ids) {
        List<JsonNode> out = new ArrayList<>();
        for (Object id : ids) {
            out.add(((ObjectNode) json(new Document("v", id))).get("v"));
        }
        return out;
    }

    /** A document as a canonical extended JSON tree. */
    static JsonNode json(Document document) {
        try {
            return FixtureLoader.JSON.readTree(canonical(document));
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    private static String canonical(Document document) {
        return document.toJson(CANONICAL);
    }

    private static Map<String, Document> byId(List<Document> documents) {
        Map<String, Document> out = new LinkedHashMap<>();
        int anonymous = 0;
        for (Document document : documents) {
            Object id = document.get("_id");
            String key = id == null ? "<no _id #" + anonymous++ + ">" : new Document("v", id).toJson(CANONICAL);
            out.put(key, document);
        }
        return out;
    }
}
