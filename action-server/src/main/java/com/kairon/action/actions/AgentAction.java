package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.actions.prompt.PromptParams;
import com.kairon.action.catalog.ActionCatalog;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.runtime.TrackerState;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.HttpCaller;
import com.kairon.action.support.Maps;
import com.kairon.action.support.PyRepr;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Singleton
public class AgentAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(AgentAction.class);

    private final ActionSupport support;

    public AgentAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "agent_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Document config = support.require("agent_action_config", context.bot, "name", context.actionName,
                "No AgentAction found for given action and bot");
        boolean dispatch = ActionFlags.enabled(config, "dispatch_bot_response");
        Object botResponse = null;
        Object apiResponse = null;
        String url = null;
        String status = Kairon.SUCCESS;
        String exception = null;
        try {
            String base = support.settings().getSimpleAgentUrl();
            // Python simple_agent.url.rstrip('/')
            base = base.replaceAll("/+$", "");
            url = base + "/agents/" + context.bot + "/" + config.get("agent_id") + "/run/" + context.tracker.senderId + "/simple";
            String token = support.tokens().integrationToken(agentClaims(context.bot, Maps.text(context.tracker.senderId)));
            Map<String, String> headers = new LinkedHashMap<>();
            headers.put("Accept", "application/json");
            headers.put("Content-Type", "application/json");
            headers.put("X-user", Maps.text(context.tracker.senderId));
            headers.put("Authorization", "Bearer " + token);
            Map<String, Object> body = new LinkedHashMap<>();
            String userMessage = context.tracker.userText() == null ? "" : context.tracker.userText();
            body.put("message", buildMessage(userMessage, chatHistory(context.tracker)));
            body.put("session_id", null);
            body.put("metadata", Map.of());
            body.put("max_iterations", 5);
            HttpCaller.Exchange exchange = support.http().exchange("POST", url, headers, body, "json");
            apiResponse = exchange.body();
            HttpCaller.validate(apiResponse, exchange.status());
            if (apiResponse instanceof Map<?, ?> map) {
                Object output = Maps.map(map).get("output");
                botResponse = Maps.isEmpty(output) ? "" : output;
            } else {
                botResponse = apiResponse == null ? "" : String.valueOf(apiResponse);
            }
            context.succeeded(botResponse);
        } catch (Exception e) {
            exception = ActionFlags.message(e);
            LOG.error("agent action failed", e);
            status = Kairon.FAIL;
            botResponse = Kairon.FAILED_DOT;
            support.failureMail(context, e);
        } finally {
            if (dispatch && Maps.truthy(botResponse)) {
                ActionFlags.utterText(context.dispatcher, botResponse);
            }
            Map<String, Object> extra = new LinkedHashMap<>();
            extra.put("url", url);
            extra.put("api_response", Maps.truthy(apiResponse) ? PyRepr.str(apiResponse) : null);
            support.save(context, type(), status, exception, botResponse, extra);
        }
        return ActionFlags.response(botResponse);
    }

    /** Token lifetime of IntegrationProcessor.create_agent_action_token (minutes). */
    static final int TOKEN_EXPIRE_MINUTES = 15;

    /**
     * IntegrationProcessor.create_agent_action_token claims. Creates the active "agent-action"
     * integration when missing, with add_integration's name-taken and limit checks.
     */
    Map<String, Object> agentClaims(String bot, String user) {
        List<Document> live = support.catalog().findLiveIntegrations(bot);
        Document integration = live.stream()
                .filter(d -> "agent-action".equals(d.get("name")) && "active".equals(d.get("status")))
                .findFirst().orElse(null);
        if (integration == null) {
            int limit = support.catalog().findBotSettings(bot)
                    .map(s -> s.get("integrations_per_user_limit")).map(v -> ((Number) v).intValue()).orElse(3);
            if (live.size() >= limit) {
                throw new ActionFailure("Integrations limit reached!");
            }
            if (live.stream().anyMatch(d -> "agent-action".equals(d.get("name")))) {
                throw new ActionFailure("Integration token with this name has already been initiated");
            }
            integration = support.catalog().insert(ActionCatalog.INTEGRATION, new Document("name", "agent-action")
                    .append("bot", bot).append("user", user)
                    .append("iat", new Date(Instant.now().truncatedTo(ChronoUnit.SECONDS).toEpochMilli()))
                    .append("role", "admin").append("status", "active"));
        }
        Document account = support.catalog().findBotById(bot)
                .orElseThrow(() -> new ActionFailure("Bot does not exists!"));
        Map<String, Object> claims = new LinkedHashMap<>();
        claims.put("sub", user);
        claims.put("bot", bot);
        claims.put("name", "agent-action");
        claims.put("role", integration.get("role"));
        claims.put("iat", ((Date) integration.get("iat")).toInstant().getEpochSecond());
        claims.put("account", account.get("account"));
        claims.put("exp", Instant.now().plusSeconds(TOKEN_EXPIRE_MINUTES * 60L).getEpochSecond());
        claims.put("access-limit", List.of("/api/agents/" + bot + "/.+/run/.+"));
        return claims;
    }

    /** Python CHAT_HISTORY_SIZE. */
    static final int CHAT_HISTORY_SIZE = 5;

    /** Python _get_chat_history: last 5 session messages, excluding the current user message. */
    static List<Map<String, Object>> chatHistory(TrackerState tracker) {
        List<Map<String, Object>> history = new ArrayList<>(PromptParams.botResponses(tracker, CHAT_HISTORY_SIZE));
        if (!history.isEmpty() && "user".equals(history.get(history.size() - 1).get("role"))) {
            history.remove(history.size() - 1);
        }
        return history.subList(Math.max(0, history.size() - CHAT_HISTORY_SIZE), history.size());
    }

    /** Python _build_message: the user message prefixed with the conversation history, if any. */
    static String buildMessage(String userMessage, List<Map<String, Object>> history) {
        if (history.isEmpty()) {
            return userMessage;
        }
        StringBuilder transcript = new StringBuilder();
        for (Map<String, Object> message : history) {
            if (transcript.length() > 0) {
                transcript.append('\n');
            }
            transcript.append(message.get("role")).append(": ").append(message.get("content"));
        }
        return "Conversation history:\n" + transcript + "\n\nCurrent message: " + userMessage;
    }
}
