package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.Maps;
import org.bson.Document;

import java.util.Map;
import java.util.Optional;

/**
 * Python retrieve_config FAQ gate: ActionUtility.get_bot_settings falls back to BotSettings(bot, status=True)
 * when no active document exists, and BotSettings.llm_settings defaults to LLMSettings(enable_faq=False).
 * A missing llm_settings or enable_faq therefore reads as disabled rather than raising.
 */
final class FaqGate {

    private FaqGate() {
    }

    /** Throws the FAQ-disabled failure unless the bot's active settings have a truthy enable_faq. */
    static void require(ActionSupport support, String bot) {
        if (!enabled(support.botSettings(bot))) {
            throw new ActionFailure(Kairon.FAQ_DISABLED);
        }
    }

    static boolean enabled(Optional<Document> settings) {
        if (settings.isEmpty() || !(settings.get().get("llm_settings") instanceof Map<?, ?> llm)) {
            return false;
        }
        return Maps.truthy(Maps.map(llm).get("enable_faq"));
    }
}
