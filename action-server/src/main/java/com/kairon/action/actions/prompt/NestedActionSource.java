package com.kairon.action.actions.prompt;

import com.kairon.action.actions.ActionFactory;
import com.kairon.action.runtime.ActionContext;
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

    static final String DATABASE_ACTION = "database_action";

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
        if (!nested.isSuccess() || DATABASE_ACTION.equals(action.type())) {
            return "";
        }
        return PromptParams.section(prompt, nested.response());
    }
}
