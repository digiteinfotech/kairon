package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;
import org.bson.Document;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Singleton
public class SlotSetAction implements KaironAction {

    private final ActionSupport support;

    public SlotSetAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "slot_set_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Document config = support.require("slot_set_action", context.bot, "name", context.actionName,
                "No Slot set action found for given action and bot");
        Map<String, Object> slots = new LinkedHashMap<>();
        List<String> messages = new ArrayList<>();
        for (Map<String, Object> slot : Maps.mapList(config.get("set_slots"))) {
            String name = Maps.str(slot.get("name"));
            if ("from_value".equals(slot.get("type"))) {
                slots.put(name, slot.get("value"));
                messages.add("Setting slot '" + name + "' to '" + slot.get("value") + "'.");
            } else {
                slots.put(name, null);
                messages.add("Resetting slot '" + name + "' value to None.");
            }
        }
        support.save(context, type(), Kairon.SUCCESS, null, null, Maps.of("messages", messages));
        return slots;
    }
}
