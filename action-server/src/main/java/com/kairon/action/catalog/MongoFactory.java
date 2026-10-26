package com.kairon.action.catalog;

import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import io.micronaut.context.annotation.Bean;
import io.micronaut.context.annotation.Factory;
import io.micronaut.context.annotation.Requires;
import io.micronaut.context.annotation.Value;
import jakarta.inject.Singleton;
import org.bson.UuidRepresentation;

@Factory
@Requires(property = "kairon.action.catalog", value = "mongo")
public class MongoFactory {

    /** Database used when DATABASE_URL names none (cavekit-config-and-deploy.md R1). */
    public static final String DEFAULT_DATABASE = "kairon";

    @Bean(preDestroy = "close")
    @Singleton
    public MongoClient mongoClient(@Value("${mongodb.uri}") String uri) {
        return MongoClients.create(clientSettings(uri));
    }

    @Singleton
    public String mongoDatabaseName(@Value("${mongodb.uri}") String uri) {
        return databaseName(uri);
    }

    /**
     * Client settings for DATABASE_URL. UUIDs use the Python legacy representation (binary subtype 3), as
     * pymongo/mongoengine write them, unless the URL sets uuidRepresentation itself.
     */
    public static MongoClientSettings clientSettings(String uri) {
        ConnectionString connection = new ConnectionString(uri);
        MongoClientSettings.Builder builder = MongoClientSettings.builder().applyConnectionString(connection);
        if (connection.getUuidRepresentation() == null) {
            builder.uuidRepresentation(UuidRepresentation.PYTHON_LEGACY);
        }
        return builder.build();
    }

    public static String databaseName(String uri) {
        String database = new ConnectionString(uri).getDatabase();
        return database == null || database.isBlank() ? DEFAULT_DATABASE : database;
    }
}
