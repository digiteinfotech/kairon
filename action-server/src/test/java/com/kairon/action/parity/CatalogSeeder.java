package com.kairon.action.parity;

import org.bson.Document;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.BiConsumer;
import java.util.function.UnaryOperator;

/**
 * Seeds the action catalog from a fixture's {@code mongo.seed} documents. Documents of every snapshotted database
 * land in the same-named collection (the catalog has no database level). Every string value, at any depth, goes
 * through {@code rewrite} so recorded upstream origins in configs point at the local stubs.
 */
final class CatalogSeeder {

    private CatalogSeeder() {
    }

    /** Inserts every seed document through {@code sink} (for example {@code MemoryActionCatalog::put}); returns the count. */
    static int seed(Fixture fixture, BiConsumer<String, Document> sink, UnaryOperator<String> rewrite) {
        int count = 0;
        for (Map.Entry<String, List<Document>> collection : fixture.mongo().seedByCollection().entrySet()) {
            for (Document document : collection.getValue()) {
                sink.accept(collection.getKey(), (Document) rewrite(document, rewrite));
                count++;
            }
        }
        return count;
    }

    static int seed(Fixture fixture, BiConsumer<String, Document> sink) {
        return seed(fixture, sink, UnaryOperator.identity());
    }

    /** Deep copy of a BSON-mapped value with {@code rewrite} applied to every string. */
    static Object rewrite(Object value, UnaryOperator<String> rewrite) {
        if (value instanceof String text) {
            return rewrite.apply(text);
        }
        if (value instanceof Map<?, ?> map) {
            Document copy = new Document();
            map.forEach((key, item) -> copy.put(String.valueOf(key), rewrite(item, rewrite)));
            return copy;
        }
        if (value instanceof List<?> list) {
            List<Object> copy = new ArrayList<>(list.size());
            list.forEach(item -> copy.add(rewrite(item, rewrite)));
            return copy;
        }
        return value;
    }
}
