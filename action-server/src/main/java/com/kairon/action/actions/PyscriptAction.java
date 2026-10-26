package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Singleton
public class PyscriptAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(PyscriptAction.class);

    private final ActionSupport support;

    public PyscriptAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "pyscript_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Document config = null;
        Object botResponse = null;
        String exception = null;
        String status = Kairon.SUCCESS;
        boolean dispatch = false;
        String dispatchType = "text";
        Map<String, Object> filled = new LinkedHashMap<>();
        List<String> messages = new ArrayList<>();
        try {
            config = support.require("pyscript_action_config", context.bot, "name", context.actionName,
                    "No pyscript action found for given action and bot");
            if (!config.containsKey("dispatch_response")) {
                throw new IllegalArgumentException("dispatch_response");
            }
            dispatch = Maps.truthy(config.get("dispatch_response"));
            Map<String, Object> response = support.runPyscript(Maps.str(config.get("source_code")), support.context(context.tracker, true));
            if (response.get("type") != null) {
                dispatchType = String.valueOf(response.get("type"));
            }
            botResponse = response.get("bot_response");
            filled.putAll(support.filterSlots(response.get("slots")));
        } catch (Exception e) {
            exception = ActionFlags.message(e);
            LOG.error("pyscript action failed", e);
            status = Kairon.FAIL;
            botResponse = Kairon.FAILED;
            support.failureMail(context, e);
        } finally {
            if (dispatch) {
                ActionSupport.Utterance uttered = support.utterLogged(context.dispatcher, dispatchType, botResponse);
                botResponse = uttered.botResponse();
                if (uttered.message() != null) {
                    messages.add(uttered.message());
                }
            }
            // ActionServerLogs(...) keyword order: config before user_msg.
            Map<String, Object> extra = new LinkedHashMap<>();
            extra.put("messages", messages);
            extra.put("config", config);
            extra.put("user_msg", context.tracker.text());
            support.save(context, type(), status, exception, botResponse, extra);
        }
        filled.put(Kairon.ACTION_RESPONSE, botResponse);
        return filled;
    }
}
