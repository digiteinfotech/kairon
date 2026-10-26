package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.HttpCaller;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

/**
 * voice_call_action (voice_call.py). Places the call through the provider's own initiate-call API, as
 * kairon/shared/voice/factory.py VoiceOutboundFactory does: Twilio (twilio.py) or Exotel (exotel/outbound.py).
 */
@Singleton
public class VoiceCallAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(VoiceCallAction.class);

    static final String TWILIO_API = "https://api.twilio.com/2010-04-01";
    static final String EXOTEL_DEFAULT_SUBDOMAIN = "api.exotel.com";

    /** ChatDataProcessor.__prepare_voice_config: required_fields of metadata voice_channels that are encrypted. */
    private static final Map<String, Set<String>> ENCRYPTED = Map.of(
            "twilio", Set.of("account_sid", "auth_token"),
            "exotel", Set.of("account_sid"));

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
            Map<String, Object> channel = channelConfig(context.bot);
            String provider = Maps.str(config.get("telephony_provider"));
            if (Maps.isEmpty(provider)) {
                provider = channel.containsKey("telephony_provider") ? Maps.str(channel.get("telephony_provider")) : "twilio";
            }
            if (!"twilio".equals(provider) && !"exotel".equals(provider)) {
                throw new ActionFailure("Unsupported voice provider: " + (provider == null ? "None" : provider));
            }
            String accountSid = Maps.str(required(channel, "account_sid"));
            String authToken = Maps.str(required(channel, "auth_token"));
            String fromNumber = Maps.str(required(channel, "phone_number"));

            Map<String, Object> phone = Maps.map(config.get("to_phone_number"));
            Object toPhone = "slot".equals(phone.get("parameter_type"))
                    ? context.tracker.slotValue(Maps.str(phone.get("value")))
                    : phone.get("value");
            if (!Maps.truthy(toPhone)) {
                throw new ActionFailure("to_phone_number is empty or slot not set");
            }
            Object callUrl = channel.containsKey("call_url") ? channel.get("call_url") : "";
            Object statusUrl = channel.containsKey("status_url") ? channel.get("status_url") : "";
            String callSid = "twilio".equals(provider)
                    ? twilioCall(accountSid, authToken, fromNumber, toPhone, callUrl, statusUrl)
                    : exotelCall(accountSid, authToken, fromNumber, toPhone, callUrl, statusUrl);

            Document log = new Document();
            log.put("type", "voice");
            log.put("status", "initiated");
            log.put("data", Maps.of("to", toPhone, "call_sid", callSid));
            log.put("message_id", Maps.isEmpty(callSid) ? "unknown" : callSid);
            log.put("bot", context.bot);
            log.put("user", channel.containsKey("user") ? channel.get("user") : "system");
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

    /** ChatDataProcessor.get_channel_config("voice", bot, mask_characters=False)["config"]. */
    private Map<String, Object> channelConfig(String bot) {
        Document channelDoc = null;
        for (Document document : support.catalog().findByBot("channels", bot)) {
            if ("voice".equals(document.get("connector_type"))) {
                channelDoc = document;
                break;
            }
        }
        if (channelDoc == null) {
            throw new ActionFailure("Channels matching query does not exist.");
        }
        Map<String, Object> channel = new LinkedHashMap<>(Maps.map(channelDoc.get("config")));
        String channelProvider = channel.containsKey("telephony_provider") ? Maps.str(channel.get("telephony_provider")) : "twilio";
        for (String field : ENCRYPTED.getOrDefault(channelProvider, Set.of())) {
            if (channel.get(field) != null) {
                channel.put(field, support.tokens().decrypt(String.valueOf(channel.get(field))));
            }
        }
        return channel;
    }

    private static Object required(Map<String, Object> channel, String key) {
        if (!channel.containsKey(key)) {
            throw new ActionFailure("'" + key + "'");
        }
        return channel.get(key);
    }

    /** TwilioOutboundClient.initiate_call: client.calls.create(to, from_, url, status_callback, status_callback_method="POST"). */
    private String twilioCall(String accountSid, String authToken, String from, Object to, Object callUrl, Object statusUrl) {
        Map<String, Object> form = twilioForm(from, to, callUrl, statusUrl);
        HttpCaller.Exchange exchange = support.http().exchange("POST", twilioCallsUrl(accountSid),
                Map.of("Authorization", HttpCaller.basic(accountSid, authToken), "Accept", "application/json"), form, "data");
        if (exchange.status() < 200 || exchange.status() >= 300) {
            Object message = Maps.map(exchange.body()).get("message");
            throw new ActionFailure("HTTP " + exchange.status() + " error: Unable to create record: "
                    + (message == null ? exchange.body() : message));
        }
        return Maps.str(Maps.map(exchange.body()).get("sid"));
    }

    static String twilioCallsUrl(String accountSid) {
        return TWILIO_API + "/Accounts/" + accountSid + "/Calls.json";
    }

    /** twilio values.of drops unset values; requests drops None-valued form fields. */
    static Map<String, Object> twilioForm(String from, Object to, Object callUrl, Object statusUrl) {
        Map<String, Object> form = new LinkedHashMap<>();
        form.put("To", to);
        form.put("From", from);
        if (callUrl != null) {
            form.put("Url", callUrl);
        }
        if (statusUrl != null) {
            form.put("StatusCallback", statusUrl);
        }
        form.put("StatusCallbackMethod", "POST");
        return form;
    }

    /**
     * ExotelOutboundClient(account_sid, auth_token, from_number).initiate_call: api_key defaults to account_sid,
     * api_token to auth_token, exophone to from_number, subdomain to api.exotel.com.
     */
    private String exotelCall(String accountSid, String authToken, String from, Object to, Object callUrl, Object statusUrl) {
        Map<String, Object> form = new LinkedHashMap<>();
        form.put("From", to);
        form.put("CallerId", from);
        form.put("Url", callUrl);
        if (Maps.truthy(statusUrl)) {
            form.put("StatusCallback", statusUrl);
            form.put("StatusCallbackMethod", "POST");
        }
        String url = "https://" + EXOTEL_DEFAULT_SUBDOMAIN + "/v1/Accounts/" + accountSid + "/Calls/connect.json";
        HttpCaller.Exchange exchange = support.http().exchange("POST", url,
                Map.of("Authorization", HttpCaller.basic(accountSid, authToken)), form, "data");
        if (exchange.status() < 200 || exchange.status() >= 300) {
            throw new ActionFailure("Exotel outbound call failed: " + exchange.status() + " " + exchange.body());
        }
        Map<String, Object> payload = Maps.map(exchange.body());
        Object call = payload.get("Call") != null ? payload.get("Call") : payload.get("call") != null ? payload.get("call") : payload;
        Map<String, Object> callMap = Maps.map(call);
        String sid = Maps.str(callMap.get("Sid") != null ? callMap.get("Sid") : callMap.get("sid"));
        if (Maps.isEmpty(sid)) {
            throw new ActionFailure("Exotel outbound call returned no Sid: " + exchange.body());
        }
        return sid;
    }
}
