package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.LinkedHashMap;
import java.util.Map;

@Singleton
public class VoiceCallAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(VoiceCallAction.class);

    private final ActionSupport support;

    public VoiceCallAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "voice_call_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Document config = support.require("voice_call_action", context.bot, "name", context.actionName,
                "No VoiceCallAction found for given action and bot");
        Object configured = config.get("response");
        Object botResponse = Maps.truthy(configured) ? configured : Kairon.CALL_OK;
        boolean dispatch = ActionFlags.enabled(config, "dispatch_bot_response");
        String status = Kairon.SUCCESS;
        String exception = null;
        try {
            Document channelDoc = null;
            for (Document document : support.catalog().findByBot("channels", context.bot)) {
                if ("voice".equals(document.get("connector_type"))) {
                    channelDoc = document;
                    break;
                }
            }
            Map<String, Object> channel = channelDoc == null ? Map.of() : Maps.map(channelDoc.get("config"));
            String provider = Maps.str(config.get("telephony_provider"));
            if (provider == null || provider.isBlank()) {
                provider = Maps.str(channel.get("telephony_provider"));
            }
            if (provider == null || provider.isBlank()) {
                provider = "twilio";
            }
            String voiceUrl = support.settings().getVoiceCallUrl();
            if (channelDoc == null || channel.isEmpty() || voiceUrl == null || voiceUrl.isBlank()) {
                throw new ActionFailure("telephony client is not configured for provider " + provider);
            }
            if (!"twilio".equals(provider) && !"exotel".equals(provider)) {
                throw new ActionFailure("Unsupported voice provider: " + provider);
            }
            Map<String, Object> phone = Maps.map(config.get("to_phone_number"));
            Object toPhone = "slot".equals(phone.get("parameter_type"))
                    ? context.tracker.slotValue(Maps.str(phone.get("value")))
                    : phone.get("value");
            if (!Maps.truthy(toPhone)) {
                throw new ActionFailure("to_phone_number is empty or slot not set");
            }
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("to", toPhone);
            body.put("from", channel.get("phone_number"));
            body.put("call_url", channel.get("call_url") == null ? "" : channel.get("call_url"));
            body.put("status_url", channel.get("status_url") == null ? "" : channel.get("status_url"));
            body.put("account_sid", channel.get("account_sid"));
            Object response = support.http().executeStrict("POST", voiceUrl, Map.of("Content-Type", "application/json"), body, "json");
            String callSid = response instanceof Map<?, ?> map && map.get("call_sid") != null
                    ? String.valueOf(map.get("call_sid"))
                    : null;
            Document log = new Document();
            log.put("type", "voice");
            log.put("status", "initiated");
            log.put("data", Maps.of("to", toPhone, "call_sid", callSid));
            log.put("message_id", callSid == null || callSid.isBlank() ? "unknown" : callSid);
            log.put("bot", context.bot);
            Object user = channel.get("user");
            log.put("user", user == null || String.valueOf(user).isBlank() ? "system" : user);
            log.put("initiator", "bot");
            support.catalog().insert("channel_logs", log);
        } catch (Exception e) {
            exception = ActionFlags.message(e);
            LOG.error("voice call action failed", e);
            status = Kairon.FAIL;
            botResponse = Kairon.CALL_FAIL;
            support.failureMail(context.bot, context.actionName, context.tracker.text(), exception);
        } finally {
            if (dispatch) {
                context.dispatcher.text(botResponse == null ? null : String.valueOf(botResponse));
            }
            support.save(context, type(), status, exception, botResponse, null);
        }
        return ActionFlags.response(botResponse);
    }
}
