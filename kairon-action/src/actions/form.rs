use serde_json::{json, Map, Value};

use super::{as_object, intent_of, save_log};
use crate::context::{evaluate_script, trigger_info, ExecCtx};
use crate::error::ActionError;
use crate::pyfmt::{is_empty, py_repr, py_str, py_truthy};

const REQUESTED_SLOT: &str = "requested_slot";

pub async fn execute(ctx: &mut ExecCtx) -> Result<Map<String, Value>, ActionError> {
    let slot_name = ctx.tracker.get_slot(REQUESTED_SLOT);
    if is_empty(&slot_name) {
        return Ok(Map::new());
    }
    let slot = slot_name.as_str().unwrap_or("").to_string();
    let mut slot_value = ctx.tracker.get_slot(&slot);
    let mut messages = vec![format!(
        "slot: {} | slot_value: {}",
        py_str(&slot_name),
        py_str(&slot_value)
    )];
    let mut status = "Failed".to_string();
    let mut propagate: Option<ActionError> = None;

    let found = ctx
        .store
        .find_one(
            "form_validation_action",
            &json!({"bot": ctx.bot, "name": ctx.action, "status": true, "slot": slot}),
        )
        .await;
    match found {
        Err(err) => propagate = Some(err),
        Ok(None) => {
            messages.push(format!(
                "Skipping validation as no validation config found for slot: {slot}"
            ));
        }
        Ok(Some(validation)) => {
            if let Err(err) = validate(ctx, &validation, &slot, &mut slot_value, &mut messages, &mut status).await
            {
                propagate = Some(err);
            }
        }
    }

    let action = ctx
        .tracker
        .followup_action
        .clone()
        .map(Value::String)
        .unwrap_or(Value::Null);
    let doc = json!({
        "type": "form_validation_action",
        "intent": intent_of(&ctx.tracker, false),
        "action": action,
        "sender": ctx.tracker.sender_id,
        "bot": ctx.tracker.get_slot("bot"),
        "messages": messages,
        "status": status,
        "trigger_info": trigger_info(&ctx.action_call),
        "request_id": ctx.request_id,
    });
    save_log(ctx.store.as_ref(), doc).await?;
    if let Some(err) = propagate {
        return Err(err);
    }
    let mut slots = Map::new();
    slots.insert(slot, slot_value);
    Ok(slots)
}

async fn validate(
    ctx: &mut ExecCtx,
    validation: &Value,
    slot: &str,
    slot_value: &mut Value,
    messages: &mut Vec<String>,
    status: &mut String,
) -> Result<(), ActionError> {
    let validation = as_object(validation, "form_validation_action")?;
    let semantic = validation
        .get("validation_semantic")
        .cloned()
        .unwrap_or(Value::Null);
    messages.push(format!("Validation Expression: {}", py_str(&semantic)));
    let is_required = match validation.get("is_required") {
        None => true,
        Some(value) => py_truthy(value),
    };
    messages.push(format!(
        "Slot is required: {}",
        if is_required { "True" } else { "False" }
    ));
    let valid_response = validation
        .get("valid_response")
        .cloned()
        .unwrap_or(Value::Null);
    let invalid_response = validation
        .get("invalid_response")
        .cloned()
        .unwrap_or(Value::Null);
    let tracker_data = crate::context::build_context(ctx.store.as_ref(), &ctx.tracker, &ctx.config, true).await?;
    let mut is_valid = false;
    if !is_empty(&semantic) {
        let script = semantic.as_str().unwrap_or("");
        let (result, log) =
            evaluate_script(&ctx.http, &ctx.config, script, &Value::Object(tracker_data)).await?;
        messages.push(format!(
            "Expression evaluation log: {}",
            py_repr(&Value::Array(log))
        ));
        messages.push(format!(
            "Expression evaluation result: {}",
            py_str(&result)
        ));
        is_valid = py_truthy(&result);
    } else if (is_required && !ctx.tracker.get_slot(slot).is_null()) || !is_required {
        is_valid = true;
    }
    if is_valid {
        *status = "Success".to_string();
        let slot_set = validation
            .get("slot_set")
            .ok_or_else(|| ActionError::failure("'NoneType' object has no attribute 'type'"))?;
        let slot_set = slot_set.as_object().ok_or_else(|| {
            ActionError::failure("'NoneType' object has no attribute 'type'")
        })?;
        let kind = slot_set.get("type").and_then(|value| value.as_str()).unwrap_or("");
        let custom = slot_set.get("value").cloned().unwrap_or(Value::Null);
        if py_truthy(&custom) && kind == "custom" {
            *slot_value = custom;
        } else if kind == "slot" {
            let name = custom.as_str().unwrap_or("");
            *slot_value = ctx.tracker.get_slot(name);
        }
        if !is_empty(&valid_response) {
            ctx.dispatcher.utter_text(valid_response);
        }
    } else {
        *slot_value = Value::Null;
        if !is_empty(&invalid_response) {
            ctx.dispatcher.utter_text(invalid_response);
        }
    }
    Ok(())
}
