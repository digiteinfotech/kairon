package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
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
public class FormValidationAction implements KaironAction {

    private final ActionSupport support;

    public FormValidationAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "form_validation_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Object requested = context.tracker.slotValue("requested_slot");
        if (Maps.isEmpty(requested)) {
            return Map.of();
        }
        String slot = String.valueOf(requested);
        Object slotValue = context.tracker.slotValue(slot);
        List<String> messages = new ArrayList<>();
        messages.add("slot: " + slot + " | slot_value: " + slotValue);
        String status = Kairon.FAIL;
        RuntimeException failure = null;
        try {
            Document validation = support.catalog().findAllActive("form_validation_action", context.bot, "name", context.actionName)
                    .stream()
                    .filter(row -> slot.equals(Maps.str(row.get("slot"))))
                    .findFirst()
                    .orElse(null);
            if (validation == null) {
                messages.add("Skipping validation as no validation config found for slot: " + slot);
            } else {
                Map<String, Object> trackerData = support.context(context.tracker, true);
                String semantic = Maps.str(validation.get("validation_semantic"));
                boolean required = !validation.containsKey("is_required") || Maps.truthy(validation.get("is_required"));
                messages.add("Validation Expression: " + semantic);
                messages.add("Slot is required: " + required);
                boolean valid;
                if (!Maps.isEmpty(semantic)) {
                    Object result = support.evaluateScript(semantic, trackerData);
                    messages.add("Expression evaluation result: " + result);
                    valid = Maps.truthy(result);
                } else {
                    valid = (required && slotValue != null) || !required;
                }
                if (valid) {
                    status = Kairon.SUCCESS;
                    Map<String, Object> slotSet = Maps.map(validation.get("slot_set"));
                    String setType = Maps.str(slotSet.get("type"));
                    Object custom = slotSet.get("value");
                    if (Maps.truthy(custom) && "custom".equals(setType)) {
                        slotValue = custom;
                    } else if ("slot".equals(setType)) {
                        slotValue = context.tracker.slotValue(Maps.str(custom));
                    }
                    String utter = Maps.str(validation.get("valid_response"));
                    if (!Maps.isEmpty(utter)) {
                        context.dispatcher.text(utter);
                    }
                } else {
                    slotValue = null;
                    String utter = Maps.str(validation.get("invalid_response"));
                    if (!Maps.isEmpty(utter)) {
                        context.dispatcher.text(utter);
                    }
                }
            }
        } catch (RuntimeException e) {
            failure = e;
        } finally {
            ActionContext logged = new ActionContext(context.bot, context.tracker.followupAction, context.tracker,
                    context.dispatcher, context.domain, context.actionCall);
            // Python form_validation ActionServerLogs(...) never passes user_msg or exception
            support.save(logged, type(), status, null, null,
                    Maps.of("messages", messages), false);
        }
        if (failure != null && !(failure instanceof ActionFailure && failure.getMessage() != null && failure.getMessage().startsWith("Skipping"))) {
            throw failure;
        }
        Map<String, Object> slots = new LinkedHashMap<>();
        slots.put(slot, slotValue);
        return slots;
    }
}
