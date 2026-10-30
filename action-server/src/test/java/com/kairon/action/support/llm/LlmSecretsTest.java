package com.kairon.action.support.llm;

import com.kairon.action.ActionSettings;
import com.kairon.action.catalog.ActionCatalog;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.support.Tokens;
import org.bson.Document;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** llm-vector-clients R6: Sysadmin.get_llm_secret / check_llm_model_exists / embedding secret. */
class LlmSecretsTest {

    private static final String FERNET = "WvNf7igjO89j9xdRtVMrW7bvVy67uV3ZM9yjwDHkC7E=";
    /** Python: Fernet(FERNET).encrypt(b"sk-python-key"). */
    private static final String PYTHON_TOKEN =
            "gAAAAABq5GoTiY0q4_nQXHPEbTCbFQswfrZNiqj4VYXomUUrhiWxPh4jzrDI48e44yMNF0gVA4-hOC7_bi5w2BtzIihM6E0ImQ==";
    private static final String BOT = "bot-1";

    private final MemoryActionCatalog catalog = new MemoryActionCatalog();
    private final Tokens tokens = tokens();
    private final LlmSecrets secrets = new LlmSecrets(catalog, tokens);

    private static Tokens tokens() {
        ActionSettings settings = new ActionSettings();
        settings.setFernetKey(FERNET);
        return new Tokens(settings);
    }

    private void seed(String bot, String llmType, String apiKey, Document extra) {
        Document document = new Document();
        if (bot != null) {
            document.put("bot", bot);
        }
        document.put("llm_type", llmType);
        document.put("api_key", apiKey);
        if (extra != null) {
            document.putAll(extra);
        }
        catalog.put(ActionCatalog.LLM_SECRET, document);
    }

    @Test
    void botSecretWinsAndDecryptsPythonFernetToken() {
        seed(null, "openai", tokens.encrypt("global-key"), null);
        seed(BOT, "openai", PYTHON_TOKEN, null);
        assertEquals(Map.of("api_key", "sk-python-key"), secrets.secret(BOT, "openai"));
    }

    @Test
    void fallsBackToGlobalSecretWithoutBotField() {
        seed("other-bot", "openai", tokens.encrypt("other-key"), null);
        seed(null, "openai", tokens.encrypt("global-key"), null);
        assertEquals("global-key", secrets.secret(BOT, "openai").get("api_key"));
    }

    @Test
    void exposesVersionAndBaseUrlOnlyWhenNonEmpty() {
        seed(BOT, "azure", tokens.encrypt("az-key"),
                new Document("api_version", "2024-02-01").append("api_base_url", "https://az.example"));
        seed(BOT, "anthropic", tokens.encrypt("an-key"),
                new Document("api_version", "  ").append("api_base_url", ""));
        Map<String, String> azure = secrets.secret(BOT, "azure");
        assertEquals(List.of("api_key", "api_version", "api_base_url"), List.copyOf(azure.keySet()));
        assertEquals("az-key", azure.get("api_key"));
        assertEquals("2024-02-01", azure.get("api_version"));
        assertEquals("https://az.example", azure.get("api_base_url"));
        assertEquals(Set.of("api_key"), secrets.secret(BOT, "anthropic").keySet());
    }

    @Test
    void blankApiKeyIsOmitted() {
        seed(BOT, "ollama", "", new Document("api_base_url", "http://ollama"));
        assertEquals(Map.of("api_base_url", "http://ollama"), secrets.secret(BOT, "ollama"));
    }

    @Test
    void missingSecretFailsWithPythonMessage() {
        seed("other-bot", "gemini", tokens.encrypt("k"), null);
        ActionFailure failure = assertThrows(ActionFailure.class, () -> secrets.secret(BOT, "gemini"));
        assertEquals("LLM secret for 'gemini' is not configured!", failure.getMessage());
    }

    @Test
    void modelCheckBotThenGlobalElseFails() {
        seed(BOT, "openai", tokens.encrypt("k"), new Document("models", List.of("gpt-4o-mini")));
        seed(null, "openai", tokens.encrypt("g"), new Document("models", List.of("gpt-4.1")));
        assertDoesNotThrow(() -> secrets.checkModel(BOT, "openai", "gpt-4o-mini"));
        assertDoesNotThrow(() -> secrets.checkModel(BOT, "openai", "gpt-4.1"));
        ActionFailure failure = assertThrows(ActionFailure.class,
                () -> secrets.checkModel(BOT, "openai", "gpt-3.5-turbo"));
        assertEquals("The model 'gpt-3.5-turbo' is not available for 'openai'.", failure.getMessage());
        ActionFailure wrongType = assertThrows(ActionFailure.class,
                () -> secrets.checkModel(BOT, "anthropic", "gpt-4.1"));
        assertEquals("The model 'gpt-4.1' is not available for 'anthropic'.", wrongType.getMessage());
    }

    @Test
    void embeddingSecretUsesOpenaiForOtherTypes() {
        seed(BOT, "openai", tokens.encrypt("openai-key"), null);
        seed(BOT, "anthropic", tokens.encrypt("anthropic-key"), null);
        seed(BOT, "openrouter", tokens.encrypt("openrouter-key"), null);
        assertEquals("openai-key", secrets.embeddingSecret(BOT, "anthropic").get("api_key"));
        assertEquals("openai-key", secrets.embeddingSecret(BOT, "openai").get("api_key"));
        assertEquals("openrouter-key", secrets.embeddingSecret(BOT, "openrouter").get("api_key"));
    }

    @Test
    void embeddingSecretMissingOpenaiFails() {
        seed(BOT, "anthropic", tokens.encrypt("anthropic-key"), null);
        ActionFailure failure = assertThrows(ActionFailure.class, () -> secrets.embeddingSecret(BOT, "anthropic"));
        assertEquals("LLM secret for 'openai' is not configured!", failure.getMessage());
    }

    @Test
    void excludedTypesAreExactlyOpenrouter() {
        assertEquals(Set.of("openrouter"), LlmSecrets.EXCLUDED_LLM_TYPES);
        assertFalse(LlmSecrets.usesDefaultEmbeddingSecret("openrouter"));
        assertFalse(LlmSecrets.usesDefaultEmbeddingSecret("openai"));
        assertTrue(LlmSecrets.usesDefaultEmbeddingSecret("anthropic"));
        assertTrue(LlmSecrets.usesDefaultEmbeddingSecret("azure"));
    }
}
