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
import java.util.Optional;

/** Calls the configured LLM endpoint. Prompt assembly, embeddings, and model checks stay on that service. */
@Singleton
public class PromptAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(PromptAction.class);

    private final ActionSupport support;

    public PromptAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "prompt_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Document config = new Document();
        Object botResponse = Kairon.DEFAULT_FALLBACK;
        Object callId = null;
        String exception = null;
        String status = Kairon.SUCCESS;
        String userMessage = null;
        Map<String, Object> filled = new LinkedHashMap<>();
        try {
            if (faqDisabled(context.bot)) {
                throw new ActionFailure(Kairon.FAQ_DISABLED);
            }
            config = support.require("prompt_action", context.bot, "name", context.actionName,
                    "No action found for given bot and name");
            userMessage = question(context, Maps.map(config.get("user_question")));
            if (Maps.isEmpty(support.settings().getLlmUrl())) {
                throw new ActionFailure("llm url is not configured");
            }
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("bot", context.bot);
            body.put("user", context.tracker.senderId);
            body.put("message", userMessage);
            body.put("llm_type", config.get("llm_type"));
            body.put("invocation", "prompt_action");
            body.put("media_ids", context.tracker.slotValue("media_ids"));
            body.put("collection", collection(config));
            body.put("hyperparameters", config.get("hyperparameters"));
            Object response = support.http().executeStrict("POST", support.settings().getLlmUrl(),
                    Map.of("Content-Type", "application/json"), body, "json");
            Map<String, Object> llm = Maps.map(response);
            if (Boolean.TRUE.equals(llm.get("is_failure"))) {
                status = Kairon.FAIL;
            }
            exception = Maps.str(llm.get("exception"));
            botResponse = llm.get("content");
            callId = llm.get("litellm_call_id");
            Map<String, Object> responseContext = new LinkedHashMap<>();
            responseContext.put("data", botResponse);
            responseContext.put("context", support.context(context.tracker, true));
            filled.putAll(support.fillSlots(config.get("set_slots"), responseContext));
        } catch (Exception e) {
            LOG.error("prompt action failed", e);
            exception = ActionFlags.message(e);
            status = Kairon.FAIL;
            if (Kairon.FAQ_DISABLED.equals(exception)) {
                botResponse = Kairon.FAQ_DISABLED;
            } else {
                Object failure = config.get("failure_message");
                botResponse = Maps.isEmpty(failure) ? Kairon.DEFAULT_FALLBACK : failure;
                support.failureMail(context.bot, context.actionName, context.tracker.text(), exception);
            }
        } finally {
            Map<String, Object> extra = new LinkedHashMap<>();
            extra.put("llm_call_id", callId);
            extra.put("user_msg", userMessage);
            support.save(context, type(), status, exception, botResponse, extra);
        }
        if (ActionFlags.enabled(config, "dispatch_response")) {
            context.dispatcher.text(botResponse == null ? null : String.valueOf(botResponse));
        }
        filled.put(Kairon.ACTION_RESPONSE, botResponse);
        filled.put(Kairon.LLM_CALL_ID, callId);
        return filled;
    }

    private boolean faqDisabled(String bot) {
        Optional<Document> settings = support.botSettings(bot);
        if (settings.isEmpty()) {
            return true;
        }
        Object llm = settings.get().get("llm_settings");
        if (!(llm instanceof Map<?, ?>)) {
            throw new ActionFailure("llm_settings");
        }
        Map<String, Object> map = Maps.map(llm);
        if (!map.containsKey("enable_faq")) {
            throw new ActionFailure("enable_faq");
        }
        return Maps.isEmpty(map.get("enable_faq"));
    }

    private static String question(ActionContext context, Map<String, Object> userQuestion) {
        if ("from_slot".equals(userQuestion.get("type"))) {
            return Maps.str(context.tracker.slotValue(Maps.str(userQuestion.get("value"))));
        }
        return context.tracker.userText();
    }

    private static String collection(Document config) {
        for (Map<String, Object> prompt : Maps.mapList(config.get("llm_prompts"))) {
            if ("user".equals(prompt.get("type")) && "bot_content".equals(prompt.get("source")) && Maps.truthy(prompt.get("is_enabled"))) {
                return Maps.str(prompt.get("data"));
            }
        }
        return null;
    }
}
