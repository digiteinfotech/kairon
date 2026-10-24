use serde_json::{json, Map, Value};

use super::{index, intent_of, load_one, not_subscriptable, save_log, text_of};
use crate::context::{
    execute_strict, format_search_result, note_failure_mail, slash_user_message, trigger_info,
    ExecCtx,
};
use crate::error::ActionError;
use crate::pyfmt::{is_empty, json_number_equal, py_str, py_truthy};

pub async fn execute(ctx: &mut ExecCtx) -> Result<Map<String, Value>, ActionError> {
    let config = load_one(
        ctx.store.as_ref(),
        "web_search_action",
        &json!({"bot": ctx.bot, "name": ctx.action, "status": true}),
        "No Public search action found for given action and bot",
    )
    .await?;
    let mut slots = Map::new();
    let mut results = Value::Null;
    let mut exception = Value::Null;
    let mut status = "Success".to_string();
    let mut bot_response = config.get("failure_response").cloned().unwrap_or(Value::Null);

    if let Err(err) = run_body(ctx, &config, &mut results, &mut bot_response, &mut slots).await {
        exception = Value::String(err.to_string());
        status = "Failed".to_string();
        note_failure_mail(&ctx.bot, &ctx.action, ctx.tracker.user_text().as_deref());
    }

    let action_name = index(&config, "name")?.clone();
    let doc = json!({
        "type": "web_search_action",
        "intent": intent_of(&ctx.tracker, false),
        "action": action_name,
        "public_search_action_response": results,
        "bot_response": bot_response,
        "sender": ctx.tracker.sender_id,
        "bot": ctx.tracker.get_slot("bot"),
        "exception": exception,
        "status": status,
        "user_msg": text_of(&ctx.tracker),
        "trigger_info": trigger_info(&ctx.action_call),
        "request_id": ctx.request_id,
    });
    save_log(ctx.store.as_ref(), doc).await?;
    if match config.get("dispatch_response") {
        None => true,
        Some(value) => py_truthy(value),
    } {
        ctx.dispatcher.utter_text(bot_response.clone());
    }
    slots.insert("kairon_action_response".into(), bot_response);
    Ok(slots)
}

async fn run_body(
    ctx: &ExecCtx,
    config: &Value,
    results: &mut Value,
    bot_response: &mut Value,
    slots: &mut Map<String, Value>,
) -> Result<(), ActionError> {
    let latest = slash_user_message(&ctx.tracker);
    if is_empty(&latest) {
        return Ok(());
    }
    let found = search(ctx, config, &latest).await?;
    *results = Value::Array(found.clone());
    if found.is_empty() {
        return Ok(());
    }
    *bot_response = Value::String(format_search_result(&found));
    let set_slot = config.get("set_slot").cloned().unwrap_or(Value::Null);
    if !is_empty(&set_slot) {
        let name = set_slot
            .as_str()
            .map(str::to_string)
            .unwrap_or_else(|| py_str(&set_slot));
        slots.insert(name, bot_response.clone());
    }
    Ok(())
}

async fn search(ctx: &ExecCtx, config: &Value, latest: &Value) -> Result<Vec<Value>, ActionError> {
    if ctx.config.web_search_trigger_task {
        return Err(ActionError::failure(
            "web search trigger_task is not available in this Rust server".to_string(),
        ));
    }
    let website = config.get("website").cloned().unwrap_or(Value::Null);
    let site = if py_truthy(&website) {
        py_str(&website)
    } else {
        String::new()
    };
    let topn = config.get("topn").cloned().unwrap_or(Value::Null);
    let body = json!({
        "text": latest,
        "site": site,
        "topn": topn,
        "bot": ctx.bot,
    });
    let url = ctx.config.web_search_url.clone().unwrap_or_default();
    let response = execute_strict(&ctx.http, &ctx.config, "POST", &url, &body, &Map::new()).await?;
    let code = response.get("error_code").unwrap_or(&Value::Null);
    if !json_number_equal(code, &json!(0)) {
        return Err(ActionError::failure(py_str(&response)));
    }
    let data = response.get("data").cloned().unwrap_or(Value::Null);
    if !py_truthy(&data) {
        return Err(ActionError::failure("No response retrieved!".to_string()));
    }
    let Some(items) = data.as_array() else {
        return Err(not_subscriptable(&data));
    };
    let mut mapped = Vec::new();
    for item in items {
        mapped.push(json!({
            "title": index(item, "title")?.clone(),
            "text": index(item, "description")?.clone(),
            "link": index(item, "url")?.clone(),
        }));
    }
    Ok(mapped)
}
