package com.kairon.action.actions.prompt;

import com.kairon.action.actions.ActionFactory;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.Maps;
import jakarta.inject.Provider;
import jakarta.inject.Singleton;

import java.util.Map;

/**
 * prompt_action user prompt with source {@code action} (kairon/actions/definitions/prompt.py, the
 * {@code LlmPromptSource.action} branch): {@code ActionFactory.get_instance(bot, prompt['data'])}, execute it with the
 * prompt action's dispatcher, tracker, domain and kwargs, and when {@code action.is_success} append
 * {@code {name}:\n{response}\n} plus the instructions block.
 *
 * <p>Success and response come from {@link ActionContext#succeeded}, which only the actions whose Python class sets
 * {@code __is_success}/{@code __response} call. A nested action that fails keeps its utterances (same dispatcher) and
 * its own log record. A nested {@code database_action} never contributes: Python's DatabaseAction never sets them.
 * Exceptions (unknown action, unsupported type, an action that raises) propagate and fail the prompt action, as in
 * Python.
 */
@Singleton
public class NestedActionSource {

    /**
     * Python classes that do NOT define an {@code is_success} property (only http, google, live_agent, agent,
     * callback, schedule and parallel do): reading it after execute raises AttributeError, which fails the
     * prompt action after the nested action already ran.
     */
    static final Map<String, String> WITHOUT_IS_SUCCESS = Map.ofEntries(
            Map.entry("slot_set_action", "ActionSetSlot"),
            Map.entry("email_action", "ActionEmail"),
            Map.entry("form_validation_action", "ActionFormValidation"),
            Map.entry("jira_action", "ActionJiraTicket"),
            Map.entry("zendesk_action", "ActionZendeskTicket"),
            Map.entry("pipedrive_leads_action", "ActionPipedriveLeads"),
            Map.entry("hubspot_forms_action", "ActionHubspotForms"),
            Map.entry("two_stage_fallback", "ActionTwoStageFallback"),
            Map.entry("kairon_bot_response", "ActionKaironBotResponse"),
            Map.entry("razorpay_action", "ActionRazorpay"),
            Map.entry("prompt_action", "ActionPrompt"),
            Map.entry("pyscript_action", "ActionPyscript"),
            Map.entry("database_action", "ActionDatabase"),
            Map.entry("web_search_action", "ActionWebSearch"),
            Map.entry("voice_call_action", "ActionVoiceCall"),
            Map.entry("voice_disconnect", "ActionVoiceDisconnect"),
            Map.entry("store_page_action", "ActionStorePage"));

    /** Provider: ActionFactory takes every KaironAction, including PromptAction, so a direct injection is a cycle. */
    private final Provider<ActionFactory> factory;

    public NestedActionSource(Provider<ActionFactory> factory) {
        this.factory = factory;
    }

    /** Context-prompt text for {@code prompt}, run on behalf of the prompt action executing in {@code parent}. */
    public String render(ActionContext parent, Map<String, Object> prompt) {
        String name = Maps.str(prompt.get("data"));
        KaironAction action = factory.get().get(parent.bot, name);
        ActionContext nested = new ActionContext(parent.bot, name, parent.tracker, parent.dispatcher,
                parent.domain, parent.actionCall);
        action.execute(nested);
        String missing = WITHOUT_IS_SUCCESS.get(action.type());
        if (missing != null) {
            throw new ActionFailure("'" + missing + "' object has no attribute 'is_success'");
        }
        if (!nested.isSuccess()) {
            return "";
        }
        return PromptParams.section(prompt, nested.response());
    }
}
