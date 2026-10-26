package com.kairon.action.parity;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.bson.Document;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Stream;

/**
 * Reads parity fixtures into {@link Fixture}. Refuses unknown schema versions and structurally invalid files
 * (missing required fields, unknown body encodings, bad header pairs) with {@link FixtureException}.
 */
final class FixtureLoader {

    static final ObjectMapper JSON = new ObjectMapper();
    private static final Set<String> ENCODINGS = Set.of("empty", "json", "text", "form", "base64");

    private FixtureLoader() {
    }

    static final class FixtureException extends RuntimeException {
        FixtureException(String message) {
            super(message);
        }
    }

    /** Every {@code *.json} directly under {@code dir}, sorted by file name. */
    static List<Fixture> loadAll(Path dir) {
        try (Stream<Path> files = Files.list(dir)) {
            List<Fixture> out = new ArrayList<>();
            for (Path file : files.filter(p -> p.getFileName().toString().endsWith(".json")).sorted().toList()) {
                out.add(load(file));
            }
            return out;
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    static Fixture load(Path file) {
        try {
            return parse(file.getFileName().toString(), Files.readString(file));
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    static Fixture loadResource(String resource) {
        try (InputStream in = FixtureLoader.class.getResourceAsStream(resource)) {
            if (in == null) {
                throw new FixtureException("no resource " + resource);
            }
            return parse(resource, new String(in.readAllBytes(), StandardCharsets.UTF_8));
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    static Fixture parse(String source, String json) {
        JsonNode root;
        try {
            root = JSON.readTree(json);
        } catch (IOException e) {
            throw new FixtureException(source + ": not JSON: " + e.getMessage());
        }
        Ctx ctx = new Ctx(source);
        ctx.object(root, "$");
        JsonNode version = ctx.field(root, "schema_version", "$");
        if (!version.isInt() || version.intValue() != Fixture.SCHEMA_VERSION) {
            throw new FixtureException(source + ": unsupported schema_version " + version + " (this harness knows "
                    + Fixture.SCHEMA_VERSION + ")");
        }
        String nodeId = ctx.text(ctx.field(root, "node_id", "$"), "$.node_id");
        if (nodeId.isEmpty()) {
            throw new FixtureException(source + ": $.node_id must not be empty");
        }
        boolean normalized = ctx.bool(ctx.field(root, "normalized", "$"), "$.normalized");
        Fixture.Mongo mongo = mongo(ctx, ctx.field(root, "mongo", "$"));
        List<Fixture.Exchange> exchanges = new ArrayList<>();
        int i = 0;
        for (JsonNode item : ctx.array(ctx.field(root, "exchanges", "$"), "$.exchanges")) {
            exchanges.add(exchange(ctx, item, "$.exchanges[" + i++ + "]"));
        }
        List<Fixture.UpstreamCall> upstream = new ArrayList<>();
        i = 0;
        for (JsonNode item : ctx.array(ctx.field(root, "upstream", "$"), "$.upstream")) {
            upstream.add(upstreamCall(ctx, item, "$.upstream[" + i++ + "]"));
        }
        return new Fixture(source, version.intValue(), nodeId, normalized, mongo, List.copyOf(exchanges), List.copyOf(upstream));
    }

    /** Canonical (or relaxed) extended JSON object to a {@link Document} with BSON types resolved. */
    static Document decodeDocument(String json) {
        return Document.parse(json);
    }

    private static Fixture.Mongo mongo(Ctx ctx, JsonNode node) {
        String at = "$.mongo";
        ctx.object(node, at);
        boolean available = ctx.bool(ctx.field(node, "available", at), at + ".available");
        List<String> databases = new ArrayList<>();
        for (JsonNode db : ctx.array(ctx.field(node, "databases", at), at + ".databases")) {
            databases.add(ctx.text(db, at + ".databases[]"));
        }
        Map<String, Map<String, List<Document>>> seed = new LinkedHashMap<>();
        for (Map.Entry<String, JsonNode> db : ctx.object(ctx.field(node, "seed", at), at + ".seed").properties()) {
            Map<String, List<Document>> collections = new LinkedHashMap<>();
            String dbAt = at + ".seed." + db.getKey();
            for (Map.Entry<String, JsonNode> coll : ctx.object(db.getValue(), dbAt).properties()) {
                collections.put(coll.getKey(), documents(ctx, coll.getValue(), dbAt + "." + coll.getKey()));
            }
            seed.put(db.getKey(), collections);
        }
        Map<String, Map<String, Fixture.Writes>> written = new LinkedHashMap<>();
        for (Map.Entry<String, JsonNode> db : ctx.object(ctx.field(node, "written", at), at + ".written").properties()) {
            Map<String, Fixture.Writes> collections = new LinkedHashMap<>();
            String dbAt = at + ".written." + db.getKey();
            for (Map.Entry<String, JsonNode> coll : ctx.object(db.getValue(), dbAt).properties()) {
                String collAt = dbAt + "." + coll.getKey();
                JsonNode writes = ctx.object(coll.getValue(), collAt);
                List<Object> deleted = new ArrayList<>();
                for (JsonNode id : ctx.array(ctx.field(writes, "deleted", collAt), collAt + ".deleted")) {
                    deleted.add(decodeValue(ctx, id, collAt + ".deleted[]"));
                }
                collections.put(coll.getKey(), new Fixture.Writes(
                        documents(ctx, ctx.field(writes, "inserted", collAt), collAt + ".inserted"),
                        documents(ctx, ctx.field(writes, "updated", collAt), collAt + ".updated"),
                        List.copyOf(deleted)));
            }
            written.put(db.getKey(), collections);
        }
        return new Fixture.Mongo(available, List.copyOf(databases), seed, written);
    }

    private static List<Document> documents(Ctx ctx, JsonNode node, String at) {
        List<Document> out = new ArrayList<>();
        int i = 0;
        for (JsonNode item : ctx.array(node, at)) {
            String itemAt = at + "[" + i++ + "]";
            ctx.object(item, itemAt);
            ctx.field(item, "_id", itemAt);
            out.add(decodeDocument(ctx, item, itemAt));
        }
        return out;
    }

    private static Document decodeDocument(Ctx ctx, JsonNode node, String at) {
        try {
            return decodeDocument(JSON.writeValueAsString(node));
        } catch (Exception e) {
            throw new FixtureException(ctx.source + ": " + at + " is not valid extended JSON: " + e.getMessage());
        }
    }

    /** Any extended JSON value (for example a deleted {@code _id}) decoded to its BSON-mapped Java value. */
    private static Object decodeValue(Ctx ctx, JsonNode node, String at) {
        ObjectNode wrapper = JsonNodeFactory.instance.objectNode();
        wrapper.set("v", node);
        return decodeDocument(ctx, wrapper, at).get("v");
    }

    private static Fixture.Exchange exchange(Ctx ctx, JsonNode node, String at) {
        ctx.object(node, at);
        String rq = at + ".request";
        JsonNode request = ctx.object(ctx.field(node, "request", at), rq);
        String path = ctx.text(ctx.field(request, "path", rq), rq + ".path");
        if (!path.startsWith("/")) {
            throw new FixtureException(ctx.source + ": " + rq + ".path must start with /");
        }
        Fixture.Request parsed = new Fixture.Request(
                ctx.text(ctx.field(request, "method", rq), rq + ".method"), path,
                ctx.text(ctx.field(request, "query", rq), rq + ".query"),
                headers(ctx, ctx.field(request, "headers", rq), rq + ".headers"),
                body(ctx, ctx.field(request, "body", rq), rq + ".body"));
        return new Fixture.Exchange(parsed, reply(ctx, ctx.field(node, "response", at), at + ".response"));
    }

    private static Fixture.UpstreamCall upstreamCall(Ctx ctx, JsonNode node, String at) {
        ctx.object(node, at);
        JsonNode seq = ctx.field(node, "seq", at);
        if (!seq.isInt() || seq.intValue() < 0) {
            throw new FixtureException(ctx.source + ": " + at + ".seq must be a non-negative integer");
        }
        String client = ctx.text(ctx.field(node, "client", at), at + ".client");
        if (!client.equals("requests") && !client.equals("aiohttp")) {
            throw new FixtureException(ctx.source + ": " + at + ".client must be requests or aiohttp");
        }
        String rq = at + ".request";
        JsonNode request = ctx.object(ctx.field(node, "request", at), rq);
        Fixture.UpstreamRequest parsed = new Fixture.UpstreamRequest(
                ctx.text(ctx.field(request, "method", rq), rq + ".method"),
                ctx.text(ctx.field(request, "url", rq), rq + ".url"),
                headers(ctx, ctx.field(request, "headers", rq), rq + ".headers"),
                body(ctx, ctx.field(request, "body", rq), rq + ".body"));
        JsonNode response = ctx.field(node, "response", at);
        JsonNode error = ctx.field(node, "error", at);
        Fixture.UpstreamError err = null;
        if (!error.isNull()) {
            ctx.object(error, at + ".error");
            err = new Fixture.UpstreamError(ctx.text(ctx.field(error, "type", at + ".error"), at + ".error.type"),
                    ctx.text(ctx.field(error, "message", at + ".error"), at + ".error.message"));
        }
        Fixture.HttpReply reply = response.isNull() ? null : reply(ctx, response, at + ".response");
        if (reply == null && err == null) {
            throw new FixtureException(ctx.source + ": " + at + " has neither response nor error");
        }
        return new Fixture.UpstreamCall(seq.intValue(), client, parsed, reply, err);
    }

    private static Fixture.HttpReply reply(Ctx ctx, JsonNode node, String at) {
        ctx.object(node, at);
        JsonNode status = ctx.field(node, "status", at);
        if (!status.isInt() || status.intValue() < 100 || status.intValue() > 599) {
            throw new FixtureException(ctx.source + ": " + at + ".status must be an integer 100..599");
        }
        return new Fixture.HttpReply(status.intValue(), headers(ctx, ctx.field(node, "headers", at), at + ".headers"),
                body(ctx, ctx.field(node, "body", at), at + ".body"));
    }

    private static List<Fixture.Header> headers(Ctx ctx, JsonNode node, String at) {
        List<Fixture.Header> out = new ArrayList<>();
        for (JsonNode pair : ctx.array(node, at)) {
            if (!pair.isArray() || pair.size() != 2 || !pair.get(0).isTextual() || !pair.get(1).isTextual()) {
                throw new FixtureException(ctx.source + ": " + at + " entries must be [name, value] string pairs");
            }
            out.add(new Fixture.Header(pair.get(0).textValue(), pair.get(1).textValue()));
        }
        return List.copyOf(out);
    }

    private static Fixture.Body body(Ctx ctx, JsonNode node, String at) {
        ctx.object(node, at);
        String encoding = ctx.text(ctx.field(node, "encoding", at), at + ".encoding");
        JsonNode value = ctx.field(node, "value", at);
        if (!ENCODINGS.contains(encoding)) {
            throw new FixtureException(ctx.source + ": " + at + ".encoding " + encoding + " is not one of " + ENCODINGS);
        }
        boolean ok = switch (encoding) {
            case "empty" -> value.isNull();
            case "text", "base64" -> value.isTextual();
            case "form" -> value.isObject();
            default -> true;
        };
        if (!ok) {
            throw new FixtureException(ctx.source + ": " + at + ".value does not fit encoding " + encoding);
        }
        return new Fixture.Body(encoding, value);
    }

    private record Ctx(String source) {
        JsonNode field(JsonNode node, String name, String at) {
            JsonNode value = node.get(name);
            if (value == null) {
                throw new FixtureException(source + ": " + at + " is missing required field " + name);
            }
            return value;
        }

        JsonNode object(JsonNode node, String at) {
            if (!node.isObject()) {
                throw new FixtureException(source + ": " + at + " must be an object");
            }
            return node;
        }

        ArrayNode array(JsonNode node, String at) {
            if (!node.isArray()) {
                throw new FixtureException(source + ": " + at + " must be an array");
            }
            return (ArrayNode) node;
        }

        String text(JsonNode node, String at) {
            if (!node.isTextual()) {
                throw new FixtureException(source + ": " + at + " must be a string");
            }
            return node.textValue();
        }

        boolean bool(JsonNode node, String at) {
            if (!node.isBoolean()) {
                throw new FixtureException(source + ": " + at + " must be a boolean");
            }
            return node.booleanValue();
        }
    }
}
