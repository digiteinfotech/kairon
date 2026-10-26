package com.kairon.action.parity;

import com.fasterxml.jackson.databind.JsonNode;
import org.bson.Document;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Typed view of one parity fixture (tests/parity/fixture-schema.md, schema_version 1). Mongo documents are decoded
 * from canonical extended JSON into BSON types (ObjectId, Date, Integer/Long/Double, Binary); HTTP bodies stay as
 * Jackson trees because they are plain JSON inside a body envelope.
 */
record Fixture(String source, int schemaVersion, String nodeId, boolean normalized, Mongo mongo,
               List<Exchange> exchanges, List<UpstreamCall> upstream) {

    static final int SCHEMA_VERSION = 1;

    record Mongo(boolean available, List<String> databases, Map<String, Map<String, List<Document>>> seed,
                 Map<String, Map<String, Writes>> written) {

        /** Seed documents of every snapshotted database, keyed by collection (the catalog has no database level). */
        Map<String, List<Document>> seedByCollection() {
            Map<String, List<Document>> out = new LinkedHashMap<>();
            seed.values().forEach(collections -> collections.forEach(
                    (name, documents) -> out.computeIfAbsent(name, key -> new ArrayList<>()).addAll(documents)));
            return out;
        }

        /** Recorded writes of every snapshotted database, keyed by collection. */
        Map<String, Writes> writtenByCollection() {
            Map<String, Writes> out = new LinkedHashMap<>();
            written.values().forEach(collections -> collections.forEach((name, writes) -> out.merge(name, writes, Writes::plus)));
            return out;
        }
    }

    /** {@code deleted} holds the removed {@code _id} values, decoded to BSON types. */
    record Writes(List<Document> inserted, List<Document> updated, List<Object> deleted) {

        static final Writes NONE = new Writes(List.of(), List.of(), List.of());

        Writes plus(Writes other) {
            List<Document> ins = new ArrayList<>(inserted);
            ins.addAll(other.inserted);
            List<Document> upd = new ArrayList<>(updated);
            upd.addAll(other.updated);
            List<Object> del = new ArrayList<>(deleted);
            del.addAll(other.deleted);
            return new Writes(ins, upd, del);
        }

        boolean isEmpty() {
            return inserted.isEmpty() && updated.isEmpty() && deleted.isEmpty();
        }
    }

    record Header(String name, String value) {}

    /** Body envelope: encoding is one of empty, json, text, form, base64. */
    record Body(String encoding, JsonNode value) {}

    record Request(String method, String path, String query, List<Header> headers, Body body) {}

    record HttpReply(int status, List<Header> headers, Body body) {}

    record Exchange(Request request, HttpReply response) {}

    record UpstreamRequest(String method, String url, List<Header> headers, Body body) {}

    record UpstreamError(String type, String message) {}

    /** {@code response} is null when the mock raised; {@code error} is then set. */
    record UpstreamCall(int seq, String client, UpstreamRequest request, HttpReply response, UpstreamError error) {}

    /** Values of header {@code name} (case-insensitive) in recorded order. */
    static List<String> values(List<Header> headers, String name) {
        List<String> out = new ArrayList<>();
        for (Header header : headers) {
            if (header.name().toLowerCase(Locale.ROOT).equals(name.toLowerCase(Locale.ROOT))) {
                out.add(header.value());
            }
        }
        return out;
    }
}
