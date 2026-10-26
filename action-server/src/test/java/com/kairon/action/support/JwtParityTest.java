package com.kairon.action.support;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.kairon.action.ActionSettings;
import org.junit.jupiter.api.Test;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

/**
 * templating-and-secrets R6: store-page and agent-integration JWTs from Tokens versus
 * kairon/shared/auth.py create_store_page_token / create_access_token / encrypt_token_claims (PyJWT 2.15.1).
 */
class JwtParityTest {

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final String FERNET = "WvNf7igjO89j9xdRtVMrW7bvVy67uV3ZM9yjwDHkC7E=";
    private static final String SECRET = "jwt-parity-secret-jwt-parity-secret-0123";
    private static final String BOT = "6697add6b8e47524eb983373";
    private static final String SENDER = "default";
    /** store_page.py:53-62 access_limit. */
    private static final List<String> ACCESS = List.of(
            "/api/bot/.+/customer_data/.*",
            "/api/bot/.+/store_page/metadata",
            "/api/bot/.+/data/collection/.*",
            "/api/bot/.+/store_page/exec/flow");

    private static Tokens tokens() {
        ActionSettings settings = new ActionSettings();
        settings.setFernetKey(FERNET);
        settings.setJwtSecret(SECRET);
        settings.setJwtAlgorithm("HS256");
        // security.token_expire must NOT leak into store-page expiry (Python uses the literal 15)
        settings.setTokenExpire(60);
        return new Tokens(settings);
    }

    private static Map<String, Object> claims() {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("sub", SENDER);
        data.put("bot", BOT);
        return data;
    }

    private static String[] parts(String jwt) {
        String[] parts = jwt.split("\\.");
        assertEquals(3, parts.length);
        return parts;
    }

    private static String segment(String part) {
        return new String(Base64.getUrlDecoder().decode(part), StandardCharsets.UTF_8);
    }

    private static Map<String, Object> read(String json) throws Exception {
        return JSON.readValue(json, new TypeReference<LinkedHashMap<String, Object>>() {});
    }

    // c1: HS256 with the configured secret
    @Test
    void signedWithHs256AndConfiguredSecret() throws Exception {
        Tokens tokens = tokens();
        for (String jwt : List.of(tokens.storePageToken(claims(), 0, ACCESS), tokens.integrationToken(claims()))) {
            String[] parts = parts(jwt);
            assertEquals("HS256", read(segment(parts[0])).get("alg"));
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(SECRET.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            byte[] expected = mac.doFinal((parts[0] + "." + parts[1]).getBytes(StandardCharsets.UTF_8));
            assertEquals(Base64.getUrlEncoder().withoutPadding().encodeToString(expected), parts[2]);
            assertTrue(!parts[0].contains("=") && !parts[1].contains("=") && !parts[2].contains("="));
        }
    }

    // c2: header bytes match PyJWT 2.15.1 (sort_headers=True): {"alg":"HS256","typ":"JWT"}
    @Test
    void headerMatchesPyJwt() {
        String header = segment(parts(tokens().integrationToken(claims()))[0]);
        assertEquals("{\"alg\":\"HS256\",\"typ\":\"JWT\"}", header);
    }

    // c3: store-page payload is exactly sub, version, exp, iat; sub is Fernet of json.dumps of the inner claims
    @Test
    void storePagePayloadAndClaims() throws Exception {
        Tokens tokens = tokens();
        long before = Instant.now().getEpochSecond();
        String jwt = tokens.storePageToken(claims(), 0, ACCESS);
        Map<String, Object> payload = read(segment(parts(jwt)[1]));
        assertEquals(List.of("sub", "version", "exp", "iat"), new ArrayList<>(payload.keySet()));
        assertEquals("2.0", payload.get("version"));
        long iat = ((Number) payload.get("iat")).longValue();
        long exp = ((Number) payload.get("exp")).longValue();
        assertTrue(iat >= before && iat <= before + 5);
        assertEquals(15 * 60, exp - iat, "default expiry is the literal 15 minutes");

        String inner = tokens.decrypt((String) payload.get("sub"));
        Map<String, Object> claims = read(inner);
        assertEquals(List.of("sub", "bot", "exp", "iat", "jti", "access-limit", "type"), new ArrayList<>(claims.keySet()));
        assertEquals(SENDER, claims.get("sub"));
        assertEquals(BOT, claims.get("bot"));
        assertEquals(exp, ((Number) claims.get("exp")).longValue());
        assertEquals(iat, ((Number) claims.get("iat")).longValue());
        assertEquals(ACCESS, claims.get("access-limit"));
        assertEquals("store_page", claims.get("type"));
        String jti = (String) claims.get("jti");
        assertTrue(jti.matches("[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"), jti);
        // json.dumps default separators
        String expected = "{\"sub\": \"" + SENDER + "\", \"bot\": \"" + BOT + "\", \"exp\": " + exp + ", \"iat\": " + iat
                + ", \"jti\": \"" + jti + "\", \"access-limit\": [\"/api/bot/.+/customer_data/.*\", \"/api/bot/.+/store_page/metadata\", "
                + "\"/api/bot/.+/data/collection/.*\", \"/api/bot/.+/store_page/exec/flow\"], \"type\": \"store_page\"}";
        assertEquals(expected, inner);
    }

    // c3: exp honours the bot's store_page_token_expiry
    @Test
    void storePageExpiryFromBotSettings() throws Exception {
        Map<String, Object> payload = read(segment(parts(tokens().storePageToken(claims(), 30, ACCESS))[1]));
        assertEquals(30 * 60, ((Number) payload.get("exp")).longValue() - ((Number) payload.get("iat")).longValue());
    }

    // c4: integration payload is exactly sub and version; inner claims {sub, bot, type: integration}
    @Test
    void integrationPayloadAndClaims() throws Exception {
        Tokens tokens = tokens();
        Map<String, Object> payload = read(segment(parts(tokens.integrationToken(claims()))[1]));
        assertEquals(List.of("sub", "version"), new ArrayList<>(payload.keySet()));
        assertEquals("2.0", payload.get("version"));
        String inner = tokens.decrypt((String) payload.get("sub"));
        assertEquals("{\"sub\": \"" + SENDER + "\", \"bot\": \"" + BOT + "\", \"type\": \"integration\"}", inner);
    }

    // c5: tokens are not byte-comparable
    @Test
    void tokensAreNotByteComparable() {
        Tokens tokens = tokens();
        assertNotEquals(tokens.integrationToken(claims()), tokens.integrationToken(claims()));
        assertNotEquals(tokens.storePageToken(claims(), 0, ACCESS), tokens.storePageToken(claims(), 0, ACCESS));
    }

    /**
     * c2 + c5 live: PyJWT verifies the port tokens with the secret (HS256 only), the Fernet sub decrypts with the
     * Python key, the header equals a PyJWT-minted header, and the claim sets equal the ones Python builds
     * (auth.py create_store_page_token / create_access_token) ignoring jti, iat and exp values.
     */
    @Test
    void pythonAcceptsPortTokens() throws Exception {
        assumeTrue(PythonBridge.available("jwt", "cryptography"), "python with PyJWT not available at " + PythonBridge.interpreter());
        Tokens tokens = tokens();
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("fernet", FERNET);
        input.put("secret", SECRET);
        input.put("sender", SENDER);
        input.put("bot", BOT);
        input.put("access", ACCESS);
        input.put("store_page", tokens.storePageToken(claims(), 0, ACCESS));
        input.put("integration", tokens.integrationToken(claims()));
        String script = String.join("\n",
                "import json, sys, base64, warnings",
                "warnings.simplefilter('ignore')",
                "import jwt",
                "from cryptography.fernet import Fernet",
                "d = json.loads(sys.stdin.read())",
                "f = Fernet(d['fernet'].encode('utf-8'))",
                "def seg(s):",
                "    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4)).decode('utf-8')",
                "def inner(token):",
                "    outer = jwt.decode(token, d['secret'], algorithms=['HS256'])",
                "    plain = f.decrypt(outer['sub'].encode('utf-8')).decode('utf-8')",
                "    return outer, plain, json.loads(plain)",
                "out = {}",
                "py_header = jwt.encode({'sub': 'x'}, d['secret'], algorithm='HS256').split('.')[0]",
                "out['header_store'] = seg(d['store_page'].split('.')[0]) == seg(py_header)",
                "out['header_integration'] = seg(d['integration'].split('.')[0]) == seg(py_header)",
                "outer, plain, c = inner(d['store_page'])",
                "expected = {'sub': d['sender'], 'bot': d['bot']}",
                "expected.update({'exp': c['exp']})",
                "expected.update({'iat': c['iat']})",
                "expected.update({'jti': c['jti']})",
                "expected['access-limit'] = d['access']",
                "expected.update({'type': 'store_page'})",
                "out['store_inner'] = plain == json.dumps(expected)",
                "out['store_outer'] = list(outer.keys()) == ['sub', 'version', 'exp', 'iat'] and outer['version'] == '2.0' and outer['exp'] == c['exp'] and outer['iat'] == c['iat']",
                "outer, plain, c = inner(d['integration'])",
                "expected = {'sub': d['sender'], 'bot': d['bot']}",
                "expected.update({'type': 'integration'})",
                "out['integration_inner'] = plain == json.dumps(expected)",
                "out['integration_outer'] = list(outer.keys()) == ['sub', 'version'] and outer['version'] == '2.0'",
                "try:",
                "    jwt.decode(d['integration'], d['secret'] + 'x', algorithms=['HS256'])",
                "    out['wrong_secret_rejected'] = False",
                "except jwt.InvalidSignatureError:",
                "    out['wrong_secret_rejected'] = True",
                "print(json.dumps(out))");
        String result = PythonBridge.run(script, JSON.writeValueAsString(input));
        Map<String, Object> checks = read(result);
        assertEquals(7, checks.size(), result);
        checks.forEach((name, ok) -> assertEquals(Boolean.TRUE, ok, name + " in " + result));
    }
}
