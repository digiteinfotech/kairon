package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.actions.prompt.CrudSource;
import com.kairon.action.actions.prompt.NestedActionSource;
import com.kairon.action.actions.prompt.PromptParams;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.Maps;
import com.kairon.action.support.PyRepr;
import com.kairon.action.support.llm.AnswerParams;
import com.kairon.action.support.llm.CognitionSchemas;
import com.kairon.action.support.llm.LlmProcessor;
import com.kairon.action.support.llm.LlmSecrets;
import jakarta.inject.Inject;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * prompt.py {@code ActionPrompt.execute}: FAQ gate, config, user question, llm params (crud / nested action sources),
 * LLMProcessor setup (llm_type secret + embedding secret), cognition schema of a non-default first similarity
 * collection (missing schema fails; training_needed false swaps to openrouter), model check on
 * {@code hyperparameters.model}, then {@link LlmProcessor#predict} against the LLM server and Qdrant.
 */
@Singleton
public class PromptAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(PromptAction.class);

    private final ActionSupport support;
    private final LlmSecrets secrets;
    private final CognitionSchemas schemas;
    private final LlmProcessor processor;

    /** {@code action} prompt source (T-114); field-injected (it depends back on the action factory). */
    @Inject
    NestedActionSource nested;

    @Inject
    public PromptAction(ActionSupport support, LlmSecrets secrets, CognitionSchemas schemas, LlmProcessor processor) {
        this.support = support;
        this.secrets = secrets;
        this.schemas = schemas;
        this.processor = processor;
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
        Object mediaIds = null;
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
            // get_faq_action_config: to_mongo() view (defaults applied, _id popped); assigned only once it is built
            config = ConfigViews.prompt(support.require("prompt_action", context.bot, "name", context.actionName,
                    "No action found for given bot and name"), () -> defaultHyperparameters());
            userMessage = PromptParams.userQuestion(Maps.map(config.get("user_question")), context.tracker);
            String llmType = Maps.str(config.get("llm_type"));
            // crud (T-113) and action (T-114) sources register ContextSource hooks here
            PromptParams.LlmParams llmParams = PromptParams.build(config, context.tracker, Map.of(
                    "crud", new CrudSource(support.catalog(), support.tokens(), context.bot, context.tracker),
                    "action", prompt -> nested.render(context, prompt)));
            // LLMProcessor(bot, llm_type): llm secret, then embedding secret; its log list exists from here on
            secrets.secret(context.bot, llmType);
            Map<String, String> embeddingSecret = secrets.embeddingSecret(context.bot, llmType);
            List<Map<String, Object>> logs = new ArrayList<>();
            llmLogs = logs;
            String endpointLlmType = llmType;
            String collection = llmParams.collection();
            if (collection != null && !collection.isEmpty() && !CognitionSchemas.DEFAULT_COLLECTION.equals(collection)) {
                CognitionSchemas.Schema schema = schemas.forAction(context.bot, collection);
                if (CognitionSchemas.swapsToOpenrouter(collection, schema)
                        && !CognitionSchemas.OPENROUTER.equals(endpointLlmType)) {
                    endpointLlmType = CognitionSchemas.OPENROUTER;
                    embeddingSecret = secrets.secret(context.bot, CognitionSchemas.OPENROUTER);
                }
            }
            if (llmParams.hyperparameters() == null) {
                throw new ActionFailure("'NoneType' object has no attribute 'get'");
            }
            Object model = Maps.map(llmParams.hyperparameters()).get("model");
            secrets.checkModel(context.bot, llmType, PyRepr.str(model));
            // Python reads media_ids only after the model check, so earlier failures log null
            mediaIds = context.tracker.slotValue("media_ids");
            AnswerParams answer = new AnswerParams(context.bot, endpointLlmType, llmType, userMessage,
                    llmParams.systemPrompt(), llmParams.contextPrompt(), context.tracker.senderId, type(),
                    mediaIds instanceof List<?> ids ? ids : null, llmParams.shouldProcessMedia(),
                    llmParams.queryPrompt(), llmParams.useQueryPrompt(), llmParams.previousBotResponses(),
                    llmParams.hyperparameters(), llmParams.instructions());
            LlmProcessor.Prediction prediction = processor.predict(answer, collection, llmParams.similarityPrompt(),
                    embeddingSecret, logs);
            Map<String, Object> llm = prediction.response();
            llmResponse = llm;
            if (prediction.isFailure()) {
                status = Kairon.FAIL;
            }
            exception = prediction.exception() == null ? null : Maps.str(prediction.exception());
            botResponse = prediction.content();
            callId = prediction.callId();
            llmElapsed = prediction.elapsedSeconds();
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
            extra.put("user_msg", userMessage);
            extra.put("media_ids", mediaIds);
            extra.put("time_elapsed", totalElapsed);
            extra.put("llm_call_id", callId);
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

    /** Utility.get_default_llm_hyperparameters (utils.py): LLMMetadata(provider=DEFAULT_LLM) property defaults. */
    private Map<String, Object> defaultHyperparameters() {
        Document metadata = support.catalog().all(LLM_METADATA).stream()
                .filter(document -> LlmSecrets.DEFAULT_LLM.equals(document.get("provider")))
                .findFirst()
                .orElseThrow(() -> new ActionFailure(
                        "Could not find any hyperparameters for " + LlmSecrets.DEFAULT_LLM + " LLM."));
        Map<String, Object> hyperparameters = new LinkedHashMap<>();
        Maps.map(metadata.get("properties")).forEach((key, value) -> {
            Map<String, Object> property = Maps.map(value);
            if (!property.containsKey("default")) {
                throw new ActionFailure("'default'");
            }
            hyperparameters.put(key, property.get("default"));
        });
        return hyperparameters;
    }

    /** mongoengine collection of LLMMetadata (kairon/shared/admin/data_objects.py). */
    static final String LLM_METADATA = "l_l_m_metadata";
}
