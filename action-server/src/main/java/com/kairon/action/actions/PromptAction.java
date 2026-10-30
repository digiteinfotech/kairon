package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.actions.prompt.PromptParams;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
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
        Object llmResponse = null;
        Object recommendations = null;
        Object llmLogs = null;
        Object mediaIds = context.tracker.slotValue("media_ids");
        Object callId = null;
        String exception = null;
        String status = Kairon.SUCCESS;
        Object userMessage = null;
        Number llmElapsed = 0;
        Number slotElapsed = 0;
        Map<String, Object> finalSlots = new LinkedHashMap<>();
        finalSlots.put("type", "slots_to_fill");
        Map<String, Object> llmResponseLog = new LinkedHashMap<>();
        llmResponseLog.put("type", "llm_response");
        List<Map<String, Object>> events = new ArrayList<>();
        Map<String, Object> filled = new LinkedHashMap<>();
        try {
            FaqGate.require(support, context.bot);
            config = support.require("prompt_action", context.bot, "name", context.actionName,
                    "No action found for given bot and name");
            userMessage = PromptParams.userQuestion(Maps.map(config.get("user_question")), context.tracker);
            if (Maps.isEmpty(support.settings().getLlmUrl())) {
                throw new ActionFailure("llm url is not configured");
            }
            // crud (T-113) and action (T-114) sources register ContextSource hooks here
            PromptParams.LlmParams llmParams = PromptParams.build(config, context.tracker, Map.of());
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("bot", context.bot);
            body.put("user", context.tracker.senderId);
            body.put("message", userMessage);
            body.put("llm_type", config.get("llm_type"));
            body.put("invocation", "prompt_action");
            body.put("media_ids", mediaIds);
            body.put("should_process_media", llmParams.shouldProcessMedia());
            body.putAll(llmParams.toMap());
            body.put("collection", llmParams.collection());
            Object response = support.http().executeStrict("POST", support.settings().getLlmUrl(),
                    Map.of("Content-Type", "application/json"), body, "json");
            Map<String, Object> llm = Maps.map(response);
            llmResponse = llm;
            if (Boolean.TRUE.equals(llm.get("is_failure"))) {
                status = Kairon.FAIL;
            }
            exception = Maps.str(llm.get("exception"));
            botResponse = llm.get("content");
            recommendations = llm.get("recommendations");
            llmLogs = llm.get("llm_logs");
            callId = llm.get("litellm_call_id");
            if (llm.get("time_elapsed") instanceof Number elapsed) {
                llmElapsed = elapsed;
            }
            Map<String, Object> responseContext = new LinkedHashMap<>();
            responseContext.put("data", botResponse);
            responseContext.put("context", support.context(context.tracker, true));
            ActionSupport.SlotFill slotFill = support.fillSlotsLogged(config.get("set_slots"), responseContext);
            filled.putAll(slotFill.values());
            slotElapsed = slotFill.elapsed();
            finalSlots.put("data", slotFill.values());
            finalSlots.put("slot_eval_log", slotFill.log());
            finalSlots.put("time_elapsed", slotFill.elapsed());
            llmResponseLog.put("response", botResponse);
            llmResponseLog.put("llm_response_log", llmResponse);
            llmResponseLog.put("time_elapsed", llmElapsed);
        } catch (Exception e) {
            LOG.error("prompt action failed", e);
            exception = ActionFlags.message(e);
            status = Kairon.FAIL;
            if (Kairon.FAQ_DISABLED.equals(exception)) {
                botResponse = Kairon.FAQ_DISABLED;
            } else {
                Object failure = config.get("failure_message");
                botResponse = Maps.isEmpty(failure) ? Kairon.DEFAULT_FALLBACK : failure;
                support.failureMail(context, e);
            }
        } finally {
            events.add(llmResponseLog);
            events.add(finalSlots);
            Number totalElapsed = llmElapsed.doubleValue() + slotElapsed.doubleValue();
            Map<String, Object> extra = new LinkedHashMap<>();
            extra.put("events", events);
            extra.put("recommendations", recommendations);
            extra.put("llm_response", llmResponse);
            extra.put("kairon_faq_action_config", logConfig(config));
            extra.put("llm_logs", llmLogs);
            extra.put("llm_call_id", callId);
            extra.put("user_msg", userMessage);
            extra.put("media_ids", mediaIds);
            extra.put("time_elapsed", totalElapsed);
            support.save(context, type(), status, exception, botResponse, extra);
        }
        if (ActionFlags.enabled(config, "dispatch_response")) {
            // Python never surfaces recommendations as buttons; always a plain text message
            context.dispatcher.text(botResponse == null ? null : String.valueOf(botResponse));
        }
        filled.put(Kairon.ACTION_RESPONSE, botResponse);
        filled.put(Kairon.LLM_CALL_ID, callId);
        return filled;
    }

    private static Document logConfig(Document config) {
        Document copy = new Document(config);
        copy.remove("_id");
        return copy;
    }
}
