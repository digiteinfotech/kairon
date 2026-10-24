use serde_json::{json, Map, Value};

use super::{custom_parameter, index, intent_of, load_one, save_log, text_of};
use crate::context::{
    build_context, execute_strict, format_search_result, note_failure_mail, slash_user_message,
    trigger_info, ExecCtx,
};
use crate::error::ActionError;
use crate::pyfmt::{is_empty, py_str, py_truthy};

pub async fn execute(ctx: &mut ExecCtx) -> Result<Map<String, Value>, ActionError> {
    let config = load_one(
        ctx.store.as_ref(),
        "google_search_action",
        &json!({"bot": ctx.bot, "name": ctx.action, "status": true}),
        "No Google search action found for given action and bot",
    )
    .await?;
    let mut slots = Map::new();
    let mut results = Value::Null;
    let mut exception = Value::Null;
    let mut status = "Success".to_string();
    let mut bot_response = config.get("failure_response").cloned().unwrap_or(Value::Null);
    let api_key_param = config.get("api_key").cloned().unwrap_or(Value::Null);

    if let Err(err) = run_body(
        ctx,
        &config,
        &api_key_param,
        &mut results,
        &mut bot_response,
        &mut slots,
    )
    .await
    {
        exception = Value::String(err.to_string());
        status = "Failed".to_string();
        note_failure_mail(&ctx.bot, &ctx.action, ctx.tracker.user_text().as_deref());
    }

    let action_name = index(&config, "name")?.clone();
    let doc = json!({
        "type": "google_search_action",
        "intent": intent_of(&ctx.tracker, false),
        "action": action_name,
        "google_response": results,
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
    api_key_param: &Value,
    results: &mut Value,
    bot_response: &mut Value,
    slots: &mut Map<String, Value>,
) -> Result<(), ActionError> {
    let latest = slash_user_message(&ctx.tracker);
    let mut tracker_data = build_context(ctx.store.as_ref(), &ctx.tracker, &ctx.config, true).await?;
    tracker_data.insert("bot".into(), Value::String(ctx.bot.clone()));
    let search_term = if config.get("search_term").map(py_truthy).unwrap_or(false) {
        custom_parameter(
            &tracker_data,
            config.get("search_term").unwrap_or(&Value::Null),
            &ctx.config,
        )?
    } else {
        latest.clone()
    };
    let api_key = custom_parameter(&tracker_data, api_key_param, &ctx.config)?;
    if is_empty(&latest) {
        return Ok(());
    }
    let engine = index(config, "search_engine_id")?.clone();
    if is_empty(&api_key) {
        return Err(ActionError::failure(
            "google search without an api key is not available in this Rust server".to_string(),
        ));
    }
    let url = google_url(
        &py_str(&api_key),
        &py_str(&engine),
        &py_str(&search_term),
        config.get("num_results"),
    );
    let body = execute_strict(
        &ctx.http,
        &ctx.config,
        "GET",
        &url,
        &json!({}),
        &Map::new(),
    )
    .await?;
    let items = match body.get("items") {
        None | Some(Value::Null) => Vec::new(),
        Some(Value::Array(items)) => items.clone(),
        Some(other) if !py_truthy(other) => Vec::new(),
        Some(other) => {
            return Err(ActionError::failure(format!(
                "'{}' object is not iterable",
                super::py_type_name(other)
            )))
        }
    };
    let mut mapped = Vec::new();
    for item in &items {
        mapped.push(json!({
            "title": index(item, "title")?.clone(),
            "text": index(item, "snippet")?.clone(),
            "link": index(item, "link")?.clone(),
        }));
    }
    *results = Value::Array(mapped.clone());
    if mapped.is_empty() {
        return Ok(());
    }
    *bot_response = Value::String(format_search_result(&mapped));
    let set_slot = config.get("set_slot").cloned().unwrap_or(Value::Null);
    if !is_empty(&set_slot) {
        let name = set_slot.as_str().map(str::to_string).unwrap_or_else(|| py_str(&set_slot));
        slots.insert(name, bot_response.clone());
    }
    Ok(())
}

fn google_url(key: &str, cx: &str, query: &str, num: Option<&Value>) -> String {
    let mut url = format!(
        "https://www.googleapis.com/customsearch/v1?key={}&cx={}&q={}",
        percent_encode(key),
        percent_encode(cx),
        percent_encode(query)
    );
    if let Some(num) = num {
        if !num.is_null() {
            url.push_str("&num=");
            url.push_str(&percent_encode(&py_str(num)));
        }
    }
    url
}

fn percent_encode(text: &str) -> String {
    let mut out = String::new();
    for byte in text.bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(byte as char)
            }
            _ => out.push_str(&format!("%{byte:02X}")),
        }
    }
    out
}
