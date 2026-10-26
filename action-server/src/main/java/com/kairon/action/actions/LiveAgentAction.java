package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.runtime.RequestIds;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.HttpCaller;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;

@Singleton
public class LiveAgentAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(LiveAgentAction.class);
    private static final Map<String, String> CHANNELS = Map.of(
            "TelegramHandler", "telegram",
            "facebook", "messenger",
            "instagram", "instagram",
            "whatsapp", "whatsapp"
    );

    private final ActionSupport support;

    public LiveAgentAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "live_agent_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        boolean dispatch = true;
        boolean web = false;
        Object botResponse = null;
        String status = Kairon.SUCCESS;
        String exception = null;
        try {
            Document config = support.require("live_agent_action_config", context.bot, "name", context.actionName,
                    "No Live Agent action found for given action and bot");
            dispatch = ActionFlags.enabled(config, "dispatch_bot_response");
            botResponse = config.get("bot_response");
            String channelKey = context.tracker.latestInputChannel();
            web = channelKey == null || channelKey.isBlank();
            String channel = web ? "web" : CHANNELS.get(channelKey);
            if (!web && channel == null) {
                throw new IllegalArgumentException(channelKey);
            }
            Map<String, Object> data = request(context, channel);
            if (Maps.truthy(data) && Maps.truthy(data.get("msg"))) {
                botResponse = data.get("msg");
                dispatch = true;
            }
        } catch (Exception e) {
            exception = ActionFlags.message(e);
            LOG.error("live agent action failed", e);
            status = Kairon.FAIL;
            if (!Maps.truthy(botResponse)) {
                botResponse = Kairon.SORRY;
            }
            support.failureMail(context, e);
        } finally {
            if (dispatch) {
                if (web) {
                    Map<String, Object> payload = new LinkedHashMap<>();
                    payload.put("action", "live_agent");
                    payload.put("response", botResponse);
                    botResponse = payload;
                    context.dispatcher.custom(payload);
                } else if (Maps.truthy(botResponse)) {
                    ActionFlags.utterText(context.dispatcher, botResponse);
                }
            } else if (web) {
                Map<String, Object> payload = new LinkedHashMap<>();
                payload.put("action", "live_agent");
                payload.put("response", null);
                botResponse = payload;
                context.dispatcher.custom(payload);
            }
            // msg_logger: the json dispatch here always gets a dict, so no conversion message is ever added.
            Map<String, Object> extra = new LinkedHashMap<>();
            extra.put("messages", new ArrayList<String>());
            support.save(context, type(), status, exception, botResponse, extra);
        }
        return Map.of();
    }

    private Map<String, Object> request(ActionContext context, String channel) {
        if (!available(context.bot)) {
            return Maps.of("msg", "Live agent service is not available");
        }
        String base = support.settings().getLiveAgentUrl();
        if (base != null && base.endsWith("/")) {
            base = base.substring(0, base.length() - 1);
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("bot_id", context.bot);
        body.put("sender_id", context.tracker.senderId);
        body.put("channel", channel);
        String requestId = RequestIds.get();
        if (requestId != null && !requestId.isBlank()) {
            body.put("request_id", requestId);
        }
        Map<String, String> headers = new LinkedHashMap<>();
        headers.put("Content-Type", "application/json");
        headers.put("Authorization", "Bearer " + support.settings().getLiveAgentToken());
        HttpCaller.Exchange exchange = support.http().exchange("POST", base + "/conversation/request", headers, body, "json");
        if (exchange.status() != 200) {
            String message = "Failed to process request";
            if (exchange.body() instanceof Map<?, ?> map && map.get("message") != null) {
                message = String.valueOf(map.get("message"));
            }
            throw new IllegalStateException(message);
        }
        if (exchange.body() instanceof Map<?, ?> map && map.get("data") instanceof Map<?, ?> data) {
            return Maps.map(data);
        }
        return Map.of();
    }

    /** Global flag off, missing settings, or live_agent_enabled false all mean unavailable. */
    private boolean available(String bot) {
        if (!support.settings().isLiveAgentEnabled()) {
            return false;
        }
        try {
            Document settings = null;
            for (Document document : support.catalog().findByBot("bot_settings", bot)) {
                settings = document;
                break;
            }
            return settings != null && Maps.truthy(settings.get("live_agent_enabled"));
        } catch (RuntimeException e) {
            LOG.error("live agent settings lookup failed", e);
            return false;
        }
    }
}
