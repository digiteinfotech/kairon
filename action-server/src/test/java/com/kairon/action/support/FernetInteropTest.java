package com.kairon.action.support;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.kairon.action.ActionSettings;
import com.kairon.action.runtime.ActionFailure;
import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

/**
 * templating-and-secrets R5: Fernet interop between Tokens and Python cryptography.Fernet
 * (kairon/shared/utils.py encrypt_message / decrypt_message, which pass no ttl).
 *
 * Vectors under src/test/resources/fernet:
 * - spec-*.json: the public Fernet spec vectors (github.com/fernet/spec, downloaded unchanged)
 * - python-vectors.json: tokens minted by Python with a throwaway test key (make_python_vectors.py)
 */
class FernetInteropTest {

    private static final ObjectMapper JSON = new ObjectMapper();

    /** invalid.json cases that are invalid only because of ttl/clock skew; Python decrypt without ttl accepts them. */
    private static final Set<String> ACCEPTED_WITHOUT_TTL = Set.of("far-future TS (unacceptable clock skew)", "expired TTL");

    private static Tokens tokens(String key) {
        ActionSettings settings = new ActionSettings();
        settings.setFernetKey(key);
        settings.setJwtSecret("unused");
        return new Tokens(settings);
    }

    private static <T> T resource(String name, TypeReference<T> type) throws Exception {
        try (InputStream in = FernetInteropTest.class.getResourceAsStream("/fernet/" + name)) {
            assertTrue(in != null, "missing resource " + name);
            return JSON.readValue(in, type);
        }
    }

    private static List<Map<String, Object>> rows(String name) throws Exception {
        return resource(name, new TypeReference<>() {});
    }

    private static Map<String, Object> pythonVectors() throws Exception {
        return resource("python-vectors.json", new TypeReference<>() {});
    }

    // c1: every vector in the public Fernet specification decrypts to its expected plaintext
    @Test
    void specGenerateAndVerifyVectorsDecrypt() throws Exception {
        List<Map<String, Object>> vectors = new ArrayList<>(rows("spec-generate.json"));
        vectors.addAll(rows("spec-verify.json"));
        assertEquals(2, vectors.size());
        for (Map<String, Object> vector : vectors) {
            String plain = tokens((String) vector.get("secret")).decrypt((String) vector.get("token"));
            assertEquals(vector.get("src"), plain);
        }
    }

    // c1 (generate.json): the token layout matches the spec: version, timestamp, iv, ciphertext, hmac
    @Test
    void specGenerateVectorLayout() throws Exception {
        Map<String, Object> vector = rows("spec-generate.json").get(0);
        byte[] raw = Base64.getUrlDecoder().decode((String) vector.get("token"));
        assertEquals((byte) 0x80, raw[0]);
        long ts = 0;
        for (int i = 1; i <= 8; i++) {
            ts = (ts << 8) | (raw[i] & 0xff);
        }
        assertEquals(Instant.parse("1985-10-26T08:20:00Z").getEpochSecond(), ts);
        @SuppressWarnings("unchecked")
        List<Integer> iv = (List<Integer>) vector.get("iv");
        for (int i = 0; i < 16; i++) {
            assertEquals(iv.get(i).byteValue(), raw[9 + i]);
        }
    }

    // c1 + c4 + c5: invalid.json — structural/mac failures raise; ttl-only failures decrypt (no TTL enforcement)
    @Test
    void specInvalidVectorsMatchPythonWithoutTtl() throws Exception {
        List<Map<String, Object>> vectors = rows("spec-invalid.json");
        assertEquals(8, vectors.size());
        int rejected = 0;
        for (Map<String, Object> vector : vectors) {
            String desc = (String) vector.get("desc");
            Tokens tokens = tokens((String) vector.get("secret"));
            String token = (String) vector.get("token");
            if (ACCEPTED_WITHOUT_TTL.contains(desc)) {
                tokens.decrypt(token);
            } else {
                assertThrows(ActionFailure.class, () -> tokens.decrypt(token), desc);
                rejected++;
            }
        }
        assertEquals(6, rejected);
    }

    // c2: a token produced by Python with the configured key decrypts in the port to the same plaintext
    @Test
    void pythonMintedTokensDecrypt() throws Exception {
        Map<String, Object> vectors = pythonVectors();
        Tokens tokens = tokens((String) vectors.get("key"));
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> cases = (List<Map<String, Object>>) vectors.get("cases");
        assertTrue(cases.size() >= 7);
        for (Map<String, Object> row : cases) {
            assertEquals(row.get("plaintext"), tokens.decrypt((String) row.get("token")));
        }
    }

    // c4: a token with a timestamp older than 60 seconds still decrypts
    @Test
    void oldTokensStillDecrypt() throws Exception {
        Map<String, Object> vectors = pythonVectors();
        @SuppressWarnings("unchecked")
        Map<String, Object> old = (Map<String, Object>) vectors.get("old_token");
        assertTrue(Instant.now().getEpochSecond() - ((Number) old.get("issued_at")).longValue() > 60);
        assertEquals(old.get("plaintext"), tokens((String) vectors.get("key")).decrypt((String) old.get("token")));
    }

    // c5: a tampered byte or the wrong key fails with an error
    @Test
    void tamperedOrWrongKeyFails() throws Exception {
        Map<String, Object> vectors = pythonVectors();
        @SuppressWarnings("unchecked")
        String token = (String) ((List<Map<String, Object>>) vectors.get("cases")).get(0).get("token");
        Tokens right = tokens((String) vectors.get("key"));
        Tokens wrong = tokens((String) vectors.get("wrong_key"));
        assertThrows(ActionFailure.class, () -> wrong.decrypt(token));
        byte[] raw = Base64.getUrlDecoder().decode(token);
        for (int index : new int[]{0, 5, 12, 30, raw.length - 40, raw.length - 1}) {
            byte[] copy = Arrays.copyOf(raw, raw.length);
            copy[index] ^= 0x01;
            String tampered = Base64.getUrlEncoder().encodeToString(copy);
            assertThrows(ActionFailure.class, () -> right.decrypt(tampered), "byte " + index);
        }
        assertThrows(ActionFailure.class, () -> right.decrypt(token.substring(0, 40)));
        assertThrows(ActionFailure.class, () -> right.decrypt("%%%%" + token.substring(4)));
    }

    // port round trip with the Python test key (format sanity before the live Python check)
    @Test
    void portRoundTripAndFormat() throws Exception {
        Tokens tokens = tokens((String) pythonVectors().get("key"));
        String token = tokens.encrypt("hello");
        assertTrue(token.startsWith("gAAAAA"));
        assertFalse(token.contains("+") || token.contains("/"));
        assertEquals(0, token.length() % 4);
        assertEquals("hello", tokens.decrypt(token));
        assertTrue(Math.abs(timestamp(token) - Instant.now().getEpochSecond()) <= 5);
    }

    // c3: a token produced by the port decrypts in Python to the same plaintext (live; skips without the venv)
    @Test
    void portMintedTokensDecryptInPython() throws Exception {
        assumeTrue(PythonBridge.available("cryptography"), "python with cryptography not available at " + PythonBridge.interpreter());
        Map<String, Object> vectors = pythonVectors();
        String key = (String) vectors.get("key");
        Tokens tokens = tokens(key);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> cases = (List<Map<String, Object>>) vectors.get("cases");
        List<Map<String, Object>> minted = new ArrayList<>();
        for (Map<String, Object> row : cases) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("plaintext", row.get("plaintext"));
            item.put("token", tokens.encrypt((String) row.get("plaintext")));
            minted.add(item);
        }
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("key", key);
        input.put("cases", minted);
        String script = String.join("\n",
                "import json, sys",
                "from cryptography.fernet import Fernet",
                "data = json.loads(sys.stdin.read())",
                "f = Fernet(data['key'].encode('utf-8'))",
                "out = [f.decrypt(c['token'].encode('utf-8')).decode('utf-8') == c['plaintext'] for c in data['cases']]",
                "print(json.dumps(out))");
        String result = PythonBridge.run(script, JSON.writeValueAsString(input));
        List<Boolean> matches = JSON.readValue(result, new TypeReference<>() {});
        assertEquals(minted.size(), matches.size());
        assertTrue(matches.stream().allMatch(Boolean::booleanValue), result);
    }

    private static long timestamp(String token) {
        byte[] raw = Base64.getUrlDecoder().decode(token.getBytes(StandardCharsets.US_ASCII));
        long ts = 0;
        for (int i = 1; i <= 8; i++) {
            ts = (ts << 8) | (raw[i] & 0xff);
        }
        return ts;
    }
}
