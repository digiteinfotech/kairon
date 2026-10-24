use serde_json::{json, Map, Value};

use super::{intent_of, load_one, missing, require, save_log, text_of};
use crate::context::{trigger_info, ExecCtx};
use crate::error::ActionError;
use crate::pyfmt::py_str;

pub async fn execute(ctx: &mut ExecCtx) -> Result<Map<String, Value>, ActionError> {
    let config = load_one(
        ctx.store.as_ref(),
        "slot_set_action",
        &json!({"bot": ctx.bot, "name": ctx.action, "status": true}),
        "No Slot set action found for given action and bot",
    )
    .await?;
    let obj = as_cfg(&config)?;
    let slots = require(obj, "set_slots")?
        .as_array()
        .ok_or_else(|| missing("set_slots"))?;
    let mut reset = Map::new();
    let mut messages = Vec::new();
    for slot in slots {
        let slot = slot
            .as_object()
            .ok_or_else(|| ActionError::failure("'set_slots' entries must be objects"))?;
        let name = require(slot, "name")?
            .as_str()
            .ok_or_else(|| missing("name"))?
            .to_string();
        let kind = require(slot, "type")?.as_str().unwrap_or("");
        if kind == "from_value" {
            let value = require(slot, "value")?.clone();
            messages.push(Value::String(format!(
                "Setting slot '{name}' to '{}'.",
                py_str(&value)
            )));
            reset.insert(name, value);
        } else {
            messages.push(Value::String(format!(
                "Resetting slot '{name}' value to None."
            )));
            reset.insert(name, Value::Null);
        }
    }
    let action_name = require(obj, "name")?.as_str().unwrap_or(&ctx.action);
    let doc = json!({
        "type": "slot_set_action",
        "intent": intent_of(&ctx.tracker, false),
        "action": action_name,
        "sender": ctx.tracker.sender_id,
        "messages": messages,
        "bot": ctx.tracker.get_slot("bot"),
        "status": "Success",
        "user_msg": text_of(&ctx.tracker),
        "trigger_info": trigger_info(&ctx.action_call),
        "request_id": ctx.request_id,
    });
    save_log(ctx.store.as_ref(), doc).await?;
    Ok(reset)
}

fn as_cfg(value: &Value) -> Result<&Map<String, Value>, ActionError> {
    super::as_object(value, "slot_set_action")
}
