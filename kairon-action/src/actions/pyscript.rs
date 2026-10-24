use serde_json::{json, Map, Value};

use super::{index, intent_of, load_one, no_attribute, save_log, text_of};
use crate::context::{
    build_context, handle_utter, log_value, note_failure_mail, run_pyscript, trigger_info, ExecCtx,
    FAILURE_TEXT,
};
use crate::error::ActionError;
use crate::pyfmt::py_truthy;

pub async fn execute(ctx: &mut ExecCtx) -> Result<Map<String, Value>, ActionError> {
    let mut config = Value::Null;
    let mut bot_response = Value::Null;
    let mut exception = Value::Null;
    let mut status = "Success".to_string();
    let mut dispatch = false;
    let mut dispatch_type = "text".to_string();
    let mut filled_slots = Map::new();
    let mut messages = Vec::new();

    if let Err(err) = run_body(
        ctx,
        &mut config,
        &mut dispatch,
        &mut dispatch_type,
        &mut bot_response,
        &mut filled_slots,
    )
    .await
    {
        exception = Value::String(err.to_string());
        status = "Failed".to_string();
        bot_response = Value::String(FAILURE_TEXT.to_string());
        note_failure_mail(&ctx.bot, &ctx.action, ctx.tracker.user_text().as_deref());
    }

    if dispatch {
        let (parsed, message) = handle_utter(&mut ctx.dispatcher, &dispatch_type, &bot_response);
        bot_response = parsed;
        if let Some(message) = message {
            messages.push(Value::String(message));
        }
    }
    let doc = json!({
        "type": "pyscript_action",
        "intent": intent_of(&ctx.tracker, false),
        "action": ctx.action,
        "config": config,
        "sender": ctx.tracker.sender_id,
        "bot_response": log_value(&bot_response),
        "messages": messages,
        "exception": exception,
        "bot": ctx.bot,
        "status": status,
        "user_msg": text_of(&ctx.tracker),
        "trigger_info": trigger_info(&ctx.action_call),
        "request_id": ctx.request_id,
    });
    save_log(ctx.store.as_ref(), doc).await?;
    filled_slots.insert("kairon_action_response".into(), bot_response);
    Ok(filled_slots)
}

async fn run_body(
    ctx: &mut ExecCtx,
    config_out: &mut Value,
    dispatch: &mut bool,
    dispatch_type: &mut String,
    bot_response: &mut Value,
    filled_slots: &mut Map<String, Value>,
) -> Result<(), ActionError> {
    let config = load_one(
        ctx.store.as_ref(),
        "pyscript_action_config",
        &json!({"bot": ctx.bot, "name": ctx.action, "status": true}),
        "No pyscript action found for given action and bot",
    )
    .await?;
    *config_out = config.clone();
    let tracker_data = build_context(ctx.store.as_ref(), &ctx.tracker, &ctx.config, true).await?;
    *dispatch = py_truthy(index(&config, "dispatch_response")?);
    let source = index(&config, "source_code")?
        .as_str()
        .unwrap_or("")
        .to_string();
    let response = run_pyscript(
        &ctx.http,
        &ctx.config,
        &source,
        &Value::Object(tracker_data),
    )
    .await?;
    let response_obj = response
        .as_object()
        .ok_or_else(|| no_attribute(&response, "get"))?;
    if let Some(kind) = response_obj.get("type").and_then(|value| value.as_str()) {
        *dispatch_type = kind.to_string();
    }
    *bot_response = response_obj
        .get("bot_response")
        .cloned()
        .unwrap_or(Value::Null);
    let slots = match response_obj.get("slots") {
        None => Map::new(),
        Some(Value::Object(map)) => map
            .iter()
            .filter(|(key, _)| key.as_str() != "bot")
            .map(|(key, value)| (key.clone(), value.clone()))
            .collect(),
        Some(other) => return Err(no_attribute(other, "items")),
    };
    crate::context::map_update(filled_slots, slots);
    Ok(())
}
