package com.kairon.action;

import com.kairon.action.support.Jsons;
import io.micronaut.context.annotation.ConfigurationProperties;
import io.micronaut.serde.annotation.Serdeable;

import java.util.ArrayList;
import java.util.List;

/**
 * Action server settings. Each value is bound in application.yml to the env var name and default of
 * the Python system.yaml key it replaces; the mapping is documented in CONFIG.md. Secrets have no default.
 */
@ConfigurationProperties("kairon.action")
@Serdeable
public class ActionSettings {

    private String catalog = "mongo";
    private String rasaSdkVersion = "3.6.21";
    /** action.request_timeout / ACTION_SERVER_REQUEST_TIMEOUT. */
    private int requestTimeout = 60;
    /** action.url / ACTION_SERVER_URL: this server's own webhook URL. */
    private String actionServerUrl = "http://localhost:5055/webhook";
    /** async_callback_action.url / ASYNC_CALLBACK_ACTION_SERVER_URL. */
    private String callbackBaseUrl = "http://localhost:5059/callback";
    /** events.server_url / EVENT_SERVER_ENDPOINT. */
    private String eventsServerUrl = "http://localhost:5056";
    /** web_search.url / WEB_SEARCH_URL. */
    private String webSearchUrl = "";
    /** evaluator.url / EXPRESSION_EVALUATOR_ENDPOINT. */
    private String evaluatorUrl = "http://192.168.100.109:8085/evaluate";
    /** async_callback_action.pyscript.url / TRIGGER_MAIN_PYSCRIPT_URL. */
    private String pyscriptUrl = "http://localhost:5059/main_pyscript/execute-python";
    /** live_agent.url / LIVE_AGENT_SERVER_URL. */
    private String liveAgentUrl = "http://localhost:8000/api/v1";
    /** live_agent.auth_token / LIVE_AGENT_AUTH_TOKEN (secret, no default). */
    private String liveAgentToken = "";
    /** live_agent.enable (no env var in Python, fixed true). */
    private boolean liveAgentEnabled = true;
    /** Adapter leftover, superseded by {@link #vectorDb}; removed in T-126. */
    private String vectorUrl = "";
    /** Adapter leftover, superseded by {@link #llmServerUrl}; removed in T-126. */
    private String llmUrl = "";
    /** llm.url / LLM_SERVER_URL. */
    private String llmServerUrl = "http://localhost";
    /** llm.request_timeout / LLM_REQUEST_TIMEOUT, seconds. */
    private int llmRequestTimeout = 30;
    /** vector.db / VECTOR_DB. */
    private String vectorDb = "http://localhost:6333";
    /** vector.key / VECTOR_DB_KEY (no default; null when unset, then no api-key header is sent). */
    private String vectorKey;
    /** simple_agent.url / SIMPLE_AGENT_URL. */
    private String simpleAgentUrl = "";
    /** Port-only: no Python key. */
    private String voiceCallUrl = "";
    /** app.frontend_url / FRONTEND_URL. */
    private String frontendUrl = "http://localhost:3000";
    /** support_mail / KAIRON_SUPPORT_MAIL. */
    private String supportMail = "kairon@digite.com";
    /** cors.origin / ALLOWED_ORIGIN, raw value: a JSON list (as Python parses it) or comma-separated. */
    private String corsOrigin = "[\"*\"]";
    /** Test-only. When set, https calls are sent to this base and keep their path and query. Empty in production. */
    private String httpsStubBase = "";
    /** security.fernet_key / FERNET_KEY (secret, no default). */
    private String fernetKey = "";
    /** security.secret_key / SECRET_KEY (secret, no default). */
    private String jwtSecret = "";
    /** security.algorithm (fixed HS256 in Python). */
    private String jwtAlgorithm = "HS256";
    /** async_callback_action.short_secret.aes_key / ASYNC_CALLBACK_AES_KEY (secret, no default). */
    private String asyncCallbackAesKey = "";
    /** async_callback_action.short_secret.aes_iv / ASYNC_CALLBACK_AES_IV (secret, no default). */
    private String asyncCallbackAesIv = "";
    /** Python code constant token_expire=15 (kairon/shared/auth.py), not a system.yaml key. */
    private int tokenExpire = 15;
    /** security.unmasked_char_count / SECRET_UNMASKED_CHAR_COUNT. */
    private int unmaskedCharCount = 2;
    /** security.unmasked_char_strategy / SECRET_UNMASKED_CHAR_STRATEGY. */
    private String unmaskedCharStrategy = "from_right";

    public String getCatalog() { return catalog; }
    public void setCatalog(String catalog) { this.catalog = catalog; }
    public String getRasaSdkVersion() { return rasaSdkVersion; }
    public void setRasaSdkVersion(String rasaSdkVersion) { this.rasaSdkVersion = rasaSdkVersion; }
    public int getRequestTimeout() { return requestTimeout; }
    public void setRequestTimeout(int requestTimeout) { this.requestTimeout = requestTimeout; }
    public String getActionServerUrl() { return actionServerUrl; }
    public void setActionServerUrl(String actionServerUrl) { this.actionServerUrl = actionServerUrl; }
    public String getCallbackBaseUrl() { return callbackBaseUrl; }
    public void setCallbackBaseUrl(String callbackBaseUrl) { this.callbackBaseUrl = callbackBaseUrl; }
    public String getEventsServerUrl() { return eventsServerUrl; }
    public void setEventsServerUrl(String eventsServerUrl) { this.eventsServerUrl = eventsServerUrl; }
    public String getWebSearchUrl() { return webSearchUrl; }
    public void setWebSearchUrl(String webSearchUrl) { this.webSearchUrl = webSearchUrl; }
    public String getEvaluatorUrl() { return evaluatorUrl; }
    public void setEvaluatorUrl(String evaluatorUrl) { this.evaluatorUrl = evaluatorUrl; }
    public String getPyscriptUrl() { return pyscriptUrl; }
    public void setPyscriptUrl(String pyscriptUrl) { this.pyscriptUrl = pyscriptUrl; }
    public String getLiveAgentUrl() { return liveAgentUrl; }
    public void setLiveAgentUrl(String liveAgentUrl) { this.liveAgentUrl = liveAgentUrl; }
    public String getLiveAgentToken() { return liveAgentToken; }
    public void setLiveAgentToken(String liveAgentToken) { this.liveAgentToken = liveAgentToken; }
    public boolean isLiveAgentEnabled() { return liveAgentEnabled; }
    public void setLiveAgentEnabled(boolean liveAgentEnabled) { this.liveAgentEnabled = liveAgentEnabled; }
    public String getVectorUrl() { return vectorUrl; }
    public void setVectorUrl(String vectorUrl) { this.vectorUrl = vectorUrl; }
    public String getLlmUrl() { return llmUrl; }
    public void setLlmUrl(String llmUrl) { this.llmUrl = llmUrl; }
    public String getLlmServerUrl() { return llmServerUrl; }
    public void setLlmServerUrl(String llmServerUrl) { this.llmServerUrl = llmServerUrl; }
    public int getLlmRequestTimeout() { return llmRequestTimeout; }
    public void setLlmRequestTimeout(int llmRequestTimeout) { this.llmRequestTimeout = llmRequestTimeout; }
    public String getVectorDb() { return vectorDb; }
    public void setVectorDb(String vectorDb) { this.vectorDb = vectorDb; }
    public String getVectorKey() { return vectorKey; }
    /** Blank is treated as unset, matching Python's unset `${VECTOR_DB_KEY}` (no api-key header). */
    public void setVectorKey(String vectorKey) {
        this.vectorKey = vectorKey == null || vectorKey.isBlank() ? null : vectorKey;
    }
    public String getSimpleAgentUrl() { return simpleAgentUrl; }
    public void setSimpleAgentUrl(String simpleAgentUrl) { this.simpleAgentUrl = simpleAgentUrl; }
    public String getVoiceCallUrl() { return voiceCallUrl; }
    public void setVoiceCallUrl(String voiceCallUrl) { this.voiceCallUrl = voiceCallUrl; }
    public String getFrontendUrl() { return frontendUrl; }
    public void setFrontendUrl(String frontendUrl) { this.frontendUrl = frontendUrl; }
    public String getSupportMail() { return supportMail; }
    public void setSupportMail(String supportMail) { this.supportMail = supportMail; }
    public String getCorsOrigin() { return corsOrigin; }
    public void setCorsOrigin(String corsOrigin) { this.corsOrigin = corsOrigin; }
    public String getHttpsStubBase() { return httpsStubBase; }
    public void setHttpsStubBase(String httpsStubBase) { this.httpsStubBase = httpsStubBase; }
    public String getFernetKey() { return fernetKey; }
    public void setFernetKey(String fernetKey) { this.fernetKey = fernetKey; }
    public String getJwtSecret() { return jwtSecret; }
    public void setJwtSecret(String jwtSecret) { this.jwtSecret = jwtSecret; }
    public String getJwtAlgorithm() { return jwtAlgorithm; }
    public void setJwtAlgorithm(String jwtAlgorithm) { this.jwtAlgorithm = jwtAlgorithm; }
    public String getAsyncCallbackAesKey() { return asyncCallbackAesKey; }
    public void setAsyncCallbackAesKey(String asyncCallbackAesKey) { this.asyncCallbackAesKey = asyncCallbackAesKey; }
    public String getAsyncCallbackAesIv() { return asyncCallbackAesIv; }
    public void setAsyncCallbackAesIv(String asyncCallbackAesIv) { this.asyncCallbackAesIv = asyncCallbackAesIv; }
    public int getTokenExpire() { return tokenExpire; }
    public void setTokenExpire(int tokenExpire) { this.tokenExpire = tokenExpire; }
    public int getUnmaskedCharCount() { return unmaskedCharCount; }
    public void setUnmaskedCharCount(int unmaskedCharCount) { this.unmaskedCharCount = unmaskedCharCount; }
    public String getUnmaskedCharStrategy() { return unmaskedCharStrategy; }
    public void setUnmaskedCharStrategy(String unmaskedCharStrategy) { this.unmaskedCharStrategy = unmaskedCharStrategy; }

    /**
     * Allowed CORS origins parsed from {@link #getCorsOrigin()}. Python's config loader json-decodes the env
     * value, so a JSON list is accepted; a plain comma-separated value is also accepted.
     */
    public List<String> corsOrigins() {
        List<String> origins = new ArrayList<>();
        String raw = corsOrigin == null ? "" : corsOrigin.trim();
        if (raw.startsWith("[")) {
            for (Object item : Jsons.asList(Jsons.readAny(raw))) {
                origins.add(String.valueOf(item));
            }
            return origins;
        }
        for (String part : raw.split(",")) {
            String origin = part.trim();
            if (origin.length() >= 2 && origin.startsWith("\"") && origin.endsWith("\"")) {
                origin = origin.substring(1, origin.length() - 1);
            }
            if (!origin.isEmpty()) {
                origins.add(origin);
            }
        }
        return origins;
    }
}
