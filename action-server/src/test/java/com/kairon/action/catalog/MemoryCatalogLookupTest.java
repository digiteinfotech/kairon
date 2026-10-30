package com.kairon.action.catalog;

import org.bson.Document;

class MemoryCatalogLookupTest extends CatalogLookupContract {

    private final MemoryActionCatalog catalog = new MemoryActionCatalog();

    @Override
    ActionCatalog catalog() {
        return catalog;
    }

    @Override
    void seed(String collection, Document document) {
        catalog.put(collection, document);
    }
}
