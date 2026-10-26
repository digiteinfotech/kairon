package com.kairon.action.config;

import com.kairon.action.catalog.MongoFactory;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import org.bson.BsonBinary;
import org.bson.BsonBinarySubType;
import org.bson.BsonDocument;
import org.bson.BsonDocumentReader;
import org.bson.BsonDocumentWriter;
import org.bson.Document;
import org.bson.UuidRepresentation;
import org.bson.codecs.Codec;
import org.bson.codecs.DecoderContext;
import org.bson.codecs.EncoderContext;
import org.bson.codecs.configuration.CodecRegistry;
import org.junit.jupiter.api.Test;

import java.nio.ByteBuffer;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;

/** cavekit-config-and-deploy.md R3 c1: UUIDs are written as binary subtype 3 (Python legacy) and read back. */
class MongoUuidTest {

    private static final UUID ID = UUID.fromString("00112233-4455-6677-8899-aabbccddeeff");

    @Test
    void clientSettingsUsePythonLegacy() {
        assertEquals(UuidRepresentation.PYTHON_LEGACY,
                MongoFactory.clientSettings("mongodb://localhost:27017/kairon").getUuidRepresentation());
    }

    @Test
    void explicitUrlOptionWins() {
        assertEquals(UuidRepresentation.STANDARD,
                MongoFactory.clientSettings("mongodb://localhost:27017/kairon?uuidRepresentation=standard").getUuidRepresentation());
    }

    @Test
    void subtype3RoundTripThroughClientCodecs() {
        MongoFactory factory = new MongoFactory();
        try (MongoClient client = factory.mongoClient("mongodb://localhost:27017/kairon?serverSelectionTimeoutMS=100")) {
            CodecRegistry registry = client.getDatabase("kairon").getCodecRegistry();
            Codec<Document> codec = registry.get(Document.class);

            BsonDocument encoded = new BsonDocument();
            codec.encode(new BsonDocumentWriter(encoded), new Document("_id", ID), EncoderContext.builder().build());
            BsonBinary binary = encoded.getBinary("_id");
            assertEquals(BsonBinarySubType.UUID_LEGACY.getValue(), binary.getType());
            // pymongo PYTHON_LEGACY stores uuid.UUID.bytes (big-endian) under subtype 3.
            assertArrayEquals(bigEndian(ID), binary.getData());

            // A subtype-3 value as Python writes it is read back as the same UUID.
            BsonDocument python = new BsonDocument("_id", new BsonBinary(BsonBinarySubType.UUID_LEGACY, bigEndian(ID)));
            Document decoded = codec.decode(new BsonDocumentReader(python), DecoderContext.builder().build());
            assertEquals(ID, decoded.get("_id"));
        }
    }

    @Test
    void defaultDriverSettingsWouldNotMatch() {
        // Guard: without the factory the driver default is UNSPECIFIED, which refuses to encode UUIDs.
        assertEquals(UuidRepresentation.UNSPECIFIED, MongoClientSettings.builder().build().getUuidRepresentation());
    }

    private static byte[] bigEndian(UUID uuid) {
        return ByteBuffer.allocate(16).putLong(uuid.getMostSignificantBits()).putLong(uuid.getLeastSignificantBits()).array();
    }
}
