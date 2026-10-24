use rand::Rng;
use serde_json::{json, Map, Value};

use super::{as_object, intent_of, missing, save_log, text_of};
use crate::context::{note_failure_mail, py_log_str, trigger_info, ExecCtx};
use crate::error::ActionError;
use crate::pyfmt::{is_empty, py_truthy};

pub async fn execute(ctx: &mut ExecCtx) -> Result<Map<String, Value>, ActionError> {
    let bot_settings = match ctx
        .store
        .find_one(
            "bot_settings",
            &json!({"bot": ctx.bot, "status": true}),
        )
        .await?
    {
        Some(doc) => doc,
        None => json!({"bot": ctx.bot, "status": true, "rephrase_response": false}),
    };
    let settings = as_object(&bot_settings, "bot_settings")?.clone();
    let responses = ctx
        .domain
        .get("responses")
        .ok_or_else(|| missing("responses"))?;
    let responses = responses
        .as_object()
        .ok_or_else(|| missing("responses"))?;
    let static_response = responses
        .get(&ctx.action)
        .cloned()
        .unwrap_or_else(|| json!([]));
    let mut bot_response = json!({"response": ctx.action});
    let mut status = "Success".to_string();
    let mut exception = Value::Null;
    let mut is_rephrased = false;
    let raw_resp = Value::Null;

    if let Err(err) = choose_response(&settings, &static_response, &mut bot_response, &mut is_rephrased)
    {
        exception = Value::String(err.to_string());
        status = "Failed".to_string();
        note_failure_mail(&ctx.bot, &ctx.action, ctx.tracker.user_text().as_deref());
    }

    let enable = settings
        .get("rephrase_response")
        .cloned()
        .ok_or_else(|| missing("rephrase_response"))?;
    let doc = json!({
        "type": "kairon_bot_response",
        "intent": intent_of(&ctx.tracker, false),
        "action": ctx.action,
        "sender": ctx.tracker.sender_id,
        "bot": ctx.bot,
        "exception": exception,
        "bot_response": py_log_str(&bot_response),
        "status": status,
        "enable_rephrasing": enable,
        "is_rephrased": is_rephrased,
        "raw_gpt_response": raw_resp,
        "user_msg": text_of(&ctx.tracker),
        "trigger_info": trigger_info(&ctx.action_call),
        "request_id": ctx.request_id,
    });
    save_log(ctx.store.as_ref(), doc).await?;
    ctx.dispatcher.utter_mapping(&bot_response);
    let mut slots = Map::new();
    slots.insert("kairon_action_response".into(), bot_response);
    Ok(slots)
}

fn choose_response(
    settings: &Map<String, Value>,
    static_response: &Value,
    bot_response: &mut Value,
    _is_rephrased: &mut bool,
) -> Result<(), ActionError> {
    let list = static_response.as_array().ok_or_else(|| {
        ActionError::failure("Cannot choose from an empty sequence".to_string())
    })?;
    if list.is_empty() {
        return Err(ActionError::failure(
            "Cannot choose from an empty sequence".to_string(),
        ));
    }
    let index = rand::thread_rng().gen_range(0..list.len());
    let chosen = &list[index];
    let text = chosen.get("text").cloned().ok_or_else(|| {
        ActionError::failure(format!(
            "'{}' object has no attribute 'get'",
            py_type(chosen)
        ))
    })?;
    if !list.is_empty()
        && py_truthy(
            settings
                .get("rephrase_response")
                .ok_or_else(|| missing("rephrase_response"))?,
        )
        && !is_empty(&text)
    {
        let _ = bot_response;
        return Err(ActionError::failure(
            "response rephrasing is not available in this Rust server".to_string(),
        ));
    }
    Ok(())
}

fn py_type(value: &Value) -> &'static str {
    match value {
        Value::Null => "NoneType",
        Value::Bool(_) => "bool",
        Value::Number(_) => "int",
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
    }
}
