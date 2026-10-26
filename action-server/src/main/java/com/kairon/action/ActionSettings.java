package com.kairon.action;

import io.micronaut.context.annotation.ConfigurationProperties;
import io.micronaut.serde.annotation.Serdeable;

@ConfigurationProperties("kairon.action")
@Serdeable
public class ActionSettings {

    private String catalog = "mongo";
    private String rasaSdkVersion = "3.6.21";
    private int requestTimeout = 5;
    private String callbackBaseUrl = "";
    private String eventsServerUrl = "";
    private String webSearchUrl = "";
    private String evaluatorUrl = "";
    private String pyscriptUrl = "";
    private String liveAgentUrl = "";
    private String liveAgentToken = "";
    private boolean liveAgentEnabled = false;
    private String vectorUrl = "";
    private String llmUrl = "";
    private String simpleAgentUrl = "";
    private String voiceCallUrl = "";
    private String frontendUrl = "";
    /** Test-only. When set, https calls are sent to this base and keep their path and query. Empty in production. */
    private String httpsStubBase = "";
    private String fernetKey = "";
    private String jwtSecret = "";
    private String jwtAlgorithm = "HS256";
    private int tokenExpire = 15;
    private int unmaskedCharCount = 4;

    public String getCatalog() { return catalog; }
    public void setCatalog(String catalog) { this.catalog = catalog; }
    public String getRasaSdkVersion() { return rasaSdkVersion; }
    public void setRasaSdkVersion(String rasaSdkVersion) { this.rasaSdkVersion = rasaSdkVersion; }
    public int getRequestTimeout() { return requestTimeout; }
    public void setRequestTimeout(int requestTimeout) { this.requestTimeout = requestTimeout; }
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
    public String getSimpleAgentUrl() { return simpleAgentUrl; }
    public void setSimpleAgentUrl(String simpleAgentUrl) { this.simpleAgentUrl = simpleAgentUrl; }
    public String getVoiceCallUrl() { return voiceCallUrl; }
    public void setVoiceCallUrl(String voiceCallUrl) { this.voiceCallUrl = voiceCallUrl; }
    public String getFrontendUrl() { return frontendUrl; }
    public void setFrontendUrl(String frontendUrl) { this.frontendUrl = frontendUrl; }
    public String getHttpsStubBase() { return httpsStubBase; }
    public void setHttpsStubBase(String httpsStubBase) { this.httpsStubBase = httpsStubBase; }
    public String getFernetKey() { return fernetKey; }
    public void setFernetKey(String fernetKey) { this.fernetKey = fernetKey; }
    public String getJwtSecret() { return jwtSecret; }
    public void setJwtSecret(String jwtSecret) { this.jwtSecret = jwtSecret; }
    public String getJwtAlgorithm() { return jwtAlgorithm; }
    public void setJwtAlgorithm(String jwtAlgorithm) { this.jwtAlgorithm = jwtAlgorithm; }
    public int getTokenExpire() { return tokenExpire; }
    public void setTokenExpire(int tokenExpire) { this.tokenExpire = tokenExpire; }
    public int getUnmaskedCharCount() { return unmaskedCharCount; }
    public void setUnmaskedCharCount(int unmaskedCharCount) { this.unmaskedCharCount = unmaskedCharCount; }
}
