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
import java.util.List;
import java.util.Map;

@Singleton
public class CallbackAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(CallbackAction.class);
    private static final Map<String, String> CHANNELS = Map.of(
            "TelegramHandler", "telegram",
            "facebook", "messenger",
            "instagram", "instagram",
            "whatsapp", "whatsapp"
    );

    private final ActionSupport support;

    public CallbackAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "callback_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Map<String, Object> filled = new LinkedHashMap<>();
        boolean dispatch = true;
        Object botResponse = null;
        String callbackUrl = null;
        Object slotName = null;
        String identifier = null;
        Object metadataLog = null;
        String status = Kairon.SUCCESS;
        String exception = null;
        try {
            Document config = support.require("callback_action_config", context.bot, "name", context.actionName,
                    "No Async Callback action found for given action and bot");
            dispatch = ActionFlags.enabled(config, "dispatch_bot_response");
            botResponse = config.get("bot_response");
            slotName = config.get("dynamic_url_slot_name");
            Object callbackName = config.get("callback_name");
            String channelKey = context.tracker.latestInputChannel();
            String channel = channelKey != null && CHANNELS.containsKey(channelKey)
                    ? CHANNELS.get(channelKey)
                    : "unsupported (" + channelKey + ")";
            Map<String, Object> trackerData = support.context(context.tracker, true, context.bot);
            Object metadataList = config.get("metadata_list") == null ? List.of() : config.get("metadata_list");
            ActionSupport.Prepared prepared = support.prepareRequestWithBot(trackerData, metadataList, context.bot);
            metadataLog = prepared.log();
            nonempty(context.actionName);
            nonempty(callbackName);
            nonempty(context.bot);
            nonempty(context.tracker.senderId);
            nonempty(channel);
            Document callback = support.callbackConfig(context.bot, String.valueOf(callbackName));
            boolean standalone = Maps.truthy(callback.get("standalone"));
            String token = support.callbackToken(callback);
            identifier = support.tokens().uuid7Hex();
            String base = support.settings().getCallbackBaseUrl() == null ? "" : support.settings().getCallbackBaseUrl();
            callbackUrl = base + "/" + (standalone ? "s/" + token : "d/" + identifier + "/" + token);
            Document record = new Document();
            record.put("action_name", context.actionName);
            record.put("callback_name", callbackName);
            record.put("bot", context.bot);
            record.put("sender_id", context.tracker.senderId);
            record.put("channel", channel);
            record.put("metadata", prepared.body());
            record.put("identifier", identifier);
            record.put("callback_url", callbackUrl);
            record.put("is_valid", true);
            support.catalog().insert("callback_data", record);
            if (slotName != null) {
                filled.put(String.valueOf(slotName), standalone ? identifier : callbackUrl);
            }
        } catch (Exception e) {
            exception = ActionFlags.message(e);
            LOG.error("callback action failed", e);
            status = Kairon.FAIL;
            if (!Maps.truthy(botResponse)) {
                botResponse = Kairon.SORRY;
            }
            support.failureMail(context.bot, context.actionName, context.tracker.text(), exception);
        } finally {
            if (dispatch) {
                if (Maps.truthy(botResponse) && Maps.truthy(callbackUrl)) {
                    botResponse = String.valueOf(botResponse).replace("{callback_url}", callbackUrl);
                }
                if (Maps.truthy(botResponse)) {
                    ActionFlags.utterText(context.dispatcher, botResponse);
                }
            }
            Map<String, Object> extra = new LinkedHashMap<>();
            extra.put("callback_url", callbackUrl);
            extra.put("callback_url_slot", slotName);
            extra.put("identifier", identifier);
            extra.put("metadata", metadataLog);
            support.save(context, type(), status, exception, botResponse, extra);
        }
        return filled;
    }

    /** Python check_nonempty_string: whitespace is allowed, blank and non-strings are not. */
    private static void nonempty(Object value) {
        if (!(value instanceof String text) || text.isEmpty()) {
            throw new ActionFailure("Value must be a non-empty string");
        }
    }
}
