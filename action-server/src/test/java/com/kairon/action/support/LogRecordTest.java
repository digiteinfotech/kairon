package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import com.kairon.action.Kairon;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.runtime.RequestIds;
import org.bson.Document;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * T-038 (log record builder), T-037 (bot_response repr), T-036 (template dict rendering),
 * T-043 (callback short token).
 */
class LogRecordTest {

    private static final String KEY = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f";
    private static final String IV = "f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff";

    @AfterEach
    void clear() {
        RequestIds.clear();
    }

    @Test
    void declaredFieldsFirstInDeclarationOrderThenDynamicNullsKept() {
        Map<String, Object> values = new LinkedHashMap<>();
        values.put("user_msg", "hi");
        values.put("request_id", "rid-1");
        values.put("status", Kairon.FAIL);
        values.put("bot", "b1");
        values.put("fail_reason", null);
        values.put("exception", "boom");
        values.put("bot_response", null);
        values.put("url", "http://x");
        values.put("type", "http_action");
        values.put("intent", "greet");
        values.put("action", "act");
        values.put("sender", "s1");
        values.put("http_status_code", 500);
        values.put("headers", Map.of());
        Document record = ActionSupport.logRecord(values);
        assertEquals(List.of("type", "intent", "action", "sender", "headers", "url", "exception", "bot", "timestamp",
                "status", "trigger_info", "request_id", "user_msg", "fail_reason", "http_status_code"),
                new ArrayList<>(record.keySet()));
        assertInstanceOf(Date.class, record.get("timestamp"));
        assertEquals(new Document("trigger_name", "").append("trigger_type", "implicit").append("trigger_id", ""),
                record.get("trigger_info"));
        // mongoengine: declared fields (null=False) drop None; dynamic kwargs become DynamicField(null=True) and keep it.
        assertFalse(record.containsKey("bot_response"));
        assertTrue(record.containsKey("fail_reason"));
        assertNull(record.get("fail_reason"));
    }

    @Test
    void dynamicNullsKeptForDatabaseAndPromptExtras() {
        Map<String, Object> values = new LinkedHashMap<>();
        values.put("type", "database_action");
        values.put("bot_response", null);
        values.put("exception", null);
        values.put("config", Map.of("name", "db"));
        values.put("payload", null);
        values.put("response", null);
        values.put("recommendations", null);
        Document record = ActionSupport.logRecord(values);
        assertEquals(List.of("type", "timestamp", "status", "trigger_info", "config", "payload", "response",
                "recommendations"), new ArrayList<>(record.keySet()));
        assertNull(record.get("payload"));
        assertNull(record.get("response"));
        assertNull(record.get("recommendations"));
    }

    @Test
    void statusDefaultsToSuccess() {
        assertEquals(Kairon.SUCCESS, ActionSupport.logRecord(Map.of("action", "a")).get("status"));
    }

    @Test
    void triggerInfoKeepsRequestValuesAndFillsDefaults() {
        Map<String, Object> requested = new LinkedHashMap<>();
        requested.put("trigger_id", "t-9");
        requested.put("trigger_type", "agentic_flow");
        requested.put("trigger_name", null);
        Document info = ActionSupport.triggerInfo(requested);
        assertEquals(List.of("trigger_name", "trigger_type", "trigger_id"), new ArrayList<>(info.keySet()));
        assertEquals("", info.get("trigger_name"));
        assertEquals("agentic_flow", info.get("trigger_type"));
        assertEquals("t-9", info.get("trigger_id"));
    }

    @Test
    void botResponseLoggedAsPythonStr() {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("response", "utter_greet");
        assertEquals("{'response': 'utter_greet'}", ActionSupport.logText(response));
        assertEquals("{'disconnect': True}", ActionSupport.logText(Map.of("disconnect", true)));
        Map<String, Object> rec = new LinkedHashMap<>();
        rec.put("text", "it's");
        rec.put("payload", "it's");
        assertEquals("[{'text': \"it's\", 'payload': \"it's\"}]", ActionSupport.logText(List.of(rec)));
        assertEquals("plain", ActionSupport.logText("plain"));
    }

    @Test
    void placeholderDictIsJsonDumpsOtherwisePythonStr() {
        ActionSupport support = new ActionSupport(new MemoryActionCatalog(), new ActionSettings(), null, null);
        Map<String, Object> response = Jsons.readMap(
                "{\"data\":{\"a\":{\"x\":1,\"y\":\"z\\u00e9\",\"n\":null},\"l\":[{\"k\":\"v\"},null,true],\"f\":2.0,\"s\":\"plain\",\"t\":false}}");
        Object out = support.prepareResponse("a=${data.a} l=${data.l} f=${data.f} s=${data.s} t=${data.t} i=${data.a.x}", response);
        // Output of Python ActionUtility.prepare_response on the same json.loads input.
        assertEquals("a={\"x\": 1, \"y\": \"z\\u00e9\", \"n\": null} l=[{'k': 'v'}, None, True] f=2.0 s=plain t=False i=1", out);
    }

    @Test
    void shortSecretMatchesPythonXorEncryptSecret() {
        // Vectors from kairon xor_encrypt_secret (cryptography AES-CTR, urlsafe_b64encode, rstrip("=")).
        assertEquals("82KuvBGl", ActionSupport.shortSecret("abc123", KEY, IV));
        assertEquals("82Gs7EL34ao7CIc1IVMCdas-GiGQS1WgD8Y0QCsW5-_4DUA6dXmU-Q", ActionSupport.shortSecret("a".repeat(40), KEY, IV));
    }

    @Test
    void shortenTokenWritesLongTokenBackAndReturnsAesHash() {
        ActionSettings settings = new ActionSettings();
        settings.setFernetKey("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=");
        settings.setAsyncCallbackAesKey(KEY);
        settings.setAsyncCallbackAesIv(IV);
        MemoryActionCatalog catalog = new MemoryActionCatalog();
        Tokens tokens = new Tokens(settings);
        catalog.put("callback_config", new Document("_id", "cb-1").append("bot", "b1").append("name", "cb")
                .append("validation_secret", tokens.encrypt("secret")).append("expire_in", 60)
                .append("shorten_token", true).append("token_hash", "abc123"));
        ActionSupport support = new ActionSupport(catalog, settings, tokens, null);
        String token = support.callbackToken(support.callbackConfig("b1", "CB"));
        assertEquals("82KuvBGl", token);
        Document stored = catalog.all("callback_config").get(0);
        Map<String, Object> claims = Jsons.readMap(tokens.decrypt(String.valueOf(stored.get("token_value"))));
        assertEquals("b1", claims.get("bot"));
        assertEquals("cb", claims.get("callback_name"));
        assertEquals("secret", claims.get("validation_secret"));
        assertEquals("abc123", stored.get("token_hash"));
    }

    @Test
    void longTokenWhenNotShortened() {
        ActionSettings settings = new ActionSettings();
        settings.setFernetKey("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=");
        MemoryActionCatalog catalog = new MemoryActionCatalog();
        Tokens tokens = new Tokens(settings);
        catalog.put("callback_config", new Document("_id", "cb-1").append("bot", "b1").append("name", "cb")
                .append("validation_secret", tokens.encrypt("secret")).append("expire_in", 60)
                .append("shorten_token", false).append("token_hash", "abc123"));
        ActionSupport support = new ActionSupport(catalog, settings, tokens, null);
        String token = support.callbackToken(support.callbackConfig("b1", "cb"));
        assertEquals("cb", Jsons.readMap(tokens.decrypt(token)).get("callback_name"));
        assertFalse(catalog.all("callback_config").get(0).containsKey("token_value"));
    }

    @Test
    void badAesKeyFails() {
        assertThrows(RuntimeException.class, () -> ActionSupport.shortSecret("x", "zz", IV));
    }
}
