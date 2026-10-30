package com.kairon.action.support.llm;

import com.kairon.action.catalog.ActionCatalog;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.support.Tokens;
import jakarta.inject.Singleton;
import org.bson.Document;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

/**
 * Sysadmin.get_llm_secret / Sysadmin.check_llm_model_exists and the LLMProcessor embedding-secret
 * choice (kairon/shared/admin/processor.py, kairon/shared/llm/processor.py).
 */
@Singleton
public class LlmSecrets {

    /** DEFAULT_LLM. */
    public static final String DEFAULT_LLM = "openai";

    /** ExcludedLLMTypes (kairon/shared/data/constant.py): these use their own secret for embeddings. */
    public static final Set<String> EXCLUDED_LLM_TYPES = Set.of("openrouter");

    private final ActionCatalog catalog;
    private final Tokens tokens;

    public LlmSecrets(ActionCatalog catalog, Tokens tokens) {
        this.catalog = catalog;
        this.tokens = tokens;
    }

    /**
     * The {bot, llm_type} secret, else the global one. Keys appear only when non-blank;
     * {@code api_key} is Fernet-decrypted.
     */
    public Map<String, String> secret(String bot, String llmType) {
        Document document = catalog.findLlmSecret(bot, llmType)
                .orElseThrow(() -> new ActionFailure("LLM secret for '" + llmType + "' is not configured!"));
        Map<String, String> result = new LinkedHashMap<>();
        String apiKey = text(document.get("api_key"));
        if (!blank(apiKey)) {
            result.put("api_key", tokens.decrypt(apiKey));
        }
        String apiVersion = text(document.get("api_version"));
        if (!blank(apiVersion)) {
            result.put("api_version", apiVersion);
        }
        String apiBaseUrl = text(document.get("api_base_url"));
        if (!blank(apiBaseUrl)) {
            result.put("api_base_url", apiBaseUrl);
        }
        return Collections.unmodifiableMap(result);
    }

    /** Fails unless {bot, llm_type} (else global) lists {@code model}. */
    public void checkModel(String bot, String llmType, String model) {
        if (catalog.findLlmModel(bot, llmType, model).isEmpty()) {
            throw new ActionFailure("The model '" + model + "' is not available for '" + llmType + "'.");
        }
    }

    /** True when embeddings use the {@code openai} secret rather than the LLM's own. */
    public static boolean usesDefaultEmbeddingSecret(String llmType) {
        return !DEFAULT_LLM.equals(llmType) && !EXCLUDED_LLM_TYPES.contains(llmType);
    }

    /** The {@code openai} secret, unless llm_type is {@code openai} or excluded; then the LLM secret. */
    public Map<String, String> embeddingSecret(String bot, String llmType) {
        return secret(bot, usesDefaultEmbeddingSecret(llmType) ? DEFAULT_LLM : llmType);
    }

    private static String text(Object value) {
        return value == null ? null : value.toString();
    }

    private static boolean blank(String value) {
        return value == null || value.strip().isEmpty();
    }
}
