package com.kairon.action.catalog;

import com.mongodb.ConnectionString;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import io.micronaut.context.annotation.Bean;
import io.micronaut.context.annotation.Factory;
import io.micronaut.context.annotation.Requires;
import io.micronaut.context.annotation.Value;
import jakarta.inject.Singleton;

@Factory
@Requires(property = "kairon.action.catalog", value = "mongo")
public class MongoFactory {

    @Bean(preDestroy = "close")
    @Singleton
    public MongoClient mongoClient(@Value("${mongodb.uri}") String uri) {
        return MongoClients.create(uri);
    }

    @Singleton
    public String mongoDatabaseName(@Value("${mongodb.uri}") String uri) {
        String database = new ConnectionString(uri).getDatabase();
        return database == null || database.isBlank() ? "conversations" : database;
    }
}
