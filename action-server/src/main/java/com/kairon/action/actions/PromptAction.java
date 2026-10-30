package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.Maps;
import com.kairon.action.support.PyRepr;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
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
        Object llmResponse = null;
        Object recommendations = null;
        Object llmLogs = null;
        Object mediaIds = context.tracker.slotValue("media_ids");
        Object callId = null;
        String exception = null;
        String status = Kairon.SUCCESS;
        String userMessage = null;
        Number llmElapsed = 0;
        Number slotElapsed = 0;
        Map<String, Object> finalSlots = new LinkedHashMap<>();
        finalSlots.put("type", "slots_to_fill");
        Map<String, Object> llmResponseLog = new LinkedHashMap<>();
        llmResponseLog.put("type", "llm_response");
        List<Map<String, Object>> events = new ArrayList<>();
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
            body.put("media_ids", mediaIds);
            body.put("should_process_media", config.get("process_media"));
            Map<String, Object> llmParams = llmParams(context, config);
            body.putAll(llmParams);
            body.put("collection", llmCollection(llmParams));
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
            if (recommendations instanceof List<?> list && !list.isEmpty()) {
                context.dispatcher.buttons(botResponse == null ? null : String.valueOf(botResponse), list);
            } else {
                context.dispatcher.text(botResponse == null ? null : String.valueOf(botResponse));
            }
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

    private static Map<String, Object> llmParams(ActionContext context, Document config) {
        String systemPrompt = null;
        StringBuilder contextPrompt = new StringBuilder();
        StringBuilder queryPrompt = new StringBuilder();
        Map<String, Object> queryPromptDict = new LinkedHashMap<>();
        List<Map<String, Object>> similarityPrompt = new ArrayList<>();
        Object historyPrompt = null;
        int numBotResponses = config.get("num_bot_responses") instanceof Number number ? number.intValue() : 0;
        for (Map<String, Object> prompt : Maps.mapList(config.get("llm_prompts"))) {
            if (!Maps.truthy(prompt.get("is_enabled"))) {
                continue;
            }
            String type = Maps.str(prompt.get("type"));
            if ("system".equals(type)) {
                systemPrompt = Maps.text(prompt.get("data")) + "\n";
                continue;
            }
            if ("user".equals(type)) {
                String source = Maps.str(prompt.get("source"));
                if ("history".equals(source)) {
                    historyPrompt = prepareBotResponses(context.tracker, numBotResponses);
                } else if ("bot_content".equals(source)) {
                    Map<String, Object> hyperparameters = Maps.map(prompt.get("hyperparameters"));
                    Map<String, Object> item = new LinkedHashMap<>();
                    item.put("similarity_prompt_name", prompt.get("name"));
                    item.put("similarity_prompt_instructions", prompt.get("instructions"));
                    item.put("collection", prompt.get("data"));
                    item.put("use_similarity_prompt", true);
                    item.put("top_results", hyperparameters.getOrDefault("top_results", 10));
                    item.put("similarity_threshold", hyperparameters.getOrDefault("similarity_threshold", 0.70));
                    similarityPrompt.add(item);
                } else if ("slot".equals(source)) {
                    Object slotData = context.tracker.slotValue(Maps.str(prompt.get("data")));
                    contextPrompt.append(Maps.text(prompt.get("name"))).append(":\n")
                            .append(PyRepr.str(slotData)).append("\n");
                    if (!Maps.isEmpty(prompt.get("instructions"))) {
                        contextPrompt.append("Instructions on how to use ")
                                .append(Maps.text(prompt.get("name"))).append(":\n")
                                .append(Maps.text(prompt.get("instructions"))).append("\n\n");
                    }
                } else {
                    contextPrompt.append(Maps.text(prompt.get("name"))).append(":\n")
                            .append(Maps.text(prompt.get("data"))).append("\n");
                    if (!Maps.isEmpty(prompt.get("instructions"))) {
                        contextPrompt.append("Instructions on how to use ")
                                .append(Maps.text(prompt.get("name"))).append(":\n")
                                .append(Maps.text(prompt.get("instructions"))).append("\n\n");
                    }
                }
                continue;
            }
            if ("query".equals(type)) {
                queryPrompt.append(Maps.text(prompt.get("name"))).append(":\n")
                        .append(Maps.text(prompt.get("data"))).append("\n");
                if (!Maps.isEmpty(prompt.get("instructions"))) {
                    queryPrompt.append("Instructions on how to use ")
                            .append(Maps.text(prompt.get("name"))).append(":\n")
                            .append(Maps.text(prompt.get("instructions"))).append("\n\n");
                }
                queryPromptDict.put("query_prompt", queryPrompt.toString());
                queryPromptDict.put("use_query_prompt", true);
            }
        }
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("hyperparameters", config.get("hyperparameters"));
        params.put("system_prompt", systemPrompt);
        params.put("context_prompt", contextPrompt.toString());
        params.put("query_prompt", queryPromptDict);
        params.put("previous_bot_responses", historyPrompt);
        params.put("similarity_prompt", similarityPrompt);
        params.put("instructions", config.getOrDefault("instructions", Collections.emptyList()));
        return params;
    }

    private static List<Map<String, Object>> prepareBotResponses(com.kairon.action.runtime.TrackerState tracker, int lastN) {
        List<Map<String, Object>> messageTrail = new ArrayList<>();
        List<Map<String, Object>> events = tracker.copyEvents();
        for (int index = events.size() - 1; index >= 0; index--) {
            Map<String, Object> event = events.get(index);
            String kind = Maps.str(event.get("event"));
            if ("bot".equals(kind) && !Maps.isEmpty(event.get("text"))) {
                messageTrail.add(0, Maps.of("role", "assistant", "content", event.get("text")));
                lastN -= 1;
            } else if ("user".equals(kind)) {
                if (!messageTrail.isEmpty() && "user".equals(Maps.str(messageTrail.get(0).get("role")))) {
                    messageTrail.remove(0);
                }
                messageTrail.add(0, Maps.of("role", "user", "content", event.get("text")));
                if (lastN <= 0) {
                    break;
                }
            } else if ("session_started".equals(kind)) {
                break;
            }
        }
        return messageTrail;
    }

    private static String llmCollection(Map<String, Object> llmParams) {
        List<Map<String, Object>> similarityPrompt = Maps.mapList(llmParams.get("similarity_prompt"));
        if (similarityPrompt.isEmpty()) {
            return null;
        }
        return Maps.str(similarityPrompt.get(0).get("collection"));
    }

    private static Document logConfig(Document config) {
        Document copy = new Document(config);
        copy.remove("_id");
        return copy;
    }
}
