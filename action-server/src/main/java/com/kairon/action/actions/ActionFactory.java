package com.kairon.action.actions;

import com.kairon.action.catalog.ActionCatalog;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;
import org.bson.Document;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

@Singleton
public class ActionFactory {

    /**
     * Types deferred to a later cycle. Their classes stay on disk but are never dispatched, so a stored
     * action of one of these types fails like any other unsupported type.
     */
    static final Set<String> DEFERRED = Set.of("prompt_action", "database_action");

    private final Map<String, KaironAction> byType = new LinkedHashMap<>();
    private final ActionCatalog catalog;

    public ActionFactory(List<KaironAction> actions, ActionCatalog catalog) {
        for (KaironAction action : actions) {
            if (!DEFERRED.contains(action.type())) {
                byType.put(action.type(), action);
            }
        }
        this.catalog = catalog;
    }

    public KaironAction get(String bot, String name) {
        String type = typeOf(bot, name);
        KaironAction action = byType.get(type);
        if (action == null) {
            throw new ActionFailure(type + " type action is not supported with action server");
        }
        return action;
    }

    public String typeOf(String bot, String name) {
        if ("kairon_voice_disconnect".equals(name)) {
            return "kairon_voice_disconnect";
        }
        if (name != null && name.startsWith("utter_")) {
            return "kairon_bot_response";
        }
        Document document = catalog.findActive("actions", bot, "name", name)
                .orElseThrow(() -> new ActionFailure("No action found for given bot and name"));
        String type = Maps.str(document.get("type"));
        return type == null ? "None" : type;
    }
}
