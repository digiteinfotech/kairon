//! Action factory and the executors that match `kairon.actions.definitions`.

mod bot_response;
mod callback;
mod email;
mod form;
mod google;
mod http;
mod pyscript;
mod slot;
mod two_stage;
mod voice;
mod web_search;

use serde_json::{json, Map, Value};

use crate::config::Config;
use crate::context::{prepare_request, ExecCtx};
use crate::error::ActionError;
use crate::pyfmt::py_truthy;
use crate::store::ActionStore;
use crate::tracker::Tracker;

const UNPORTED: &[&str] = &[
    "jira_action",
    "zendesk_action",
    "pipedrive_leads_action",
    "hubspot_forms_action",
    "razorpay_action",
    "prompt_action",
    "database_action",
    "live_agent_action",
    "schedule_action",
    "parallel_action",
    "voice_call_action",
    "store_page_action",
    "agent_action",
];

pub async fn run(ctx: &mut ExecCtx) -> Result<Map<String, Value>, ActionError> {
    let kind = resolve_type(ctx).await?;
    match kind.as_str() {
        "http_action" => http::execute(ctx).await,
        "slot_set_action" => slot::execute(ctx).await,
        "form_validation_action" => form::execute(ctx).await,
        "email_action" => email::execute(ctx).await,
        "google_search_action" => google::execute(ctx).await,
        "kairon_bot_response" => bot_response::execute(ctx).await,
        "pyscript_action" => pyscript::execute(ctx).await,
        "web_search_action" => web_search::execute(ctx).await,
        "two_stage_fallback" => two_stage::execute(ctx).await,
        "callback_action" => callback::execute(ctx).await,
        "kairon_voice_disconnect" => voice::execute(ctx).await,
        other if UNPORTED.contains(&other) => Err(ActionError::failure(format!(
            "{other} is not available in this Rust action server"
        ))),
        other => Err(ActionError::failure(format!(
            "{other} type action is not supported with action server"
        ))),
    }
}

async fn resolve_type(ctx: &ExecCtx) -> Result<String, ActionError> {
    if ctx.action == "kairon_voice_disconnect" {
        return Ok("kairon_voice_disconnect".to_string());
    }
    if ctx.action.starts_with("utter_") {
        return Ok("kairon_bot_response".to_string());
    }
    let found = ctx
        .store
        .find_one(
            "actions",
            &json!({"bot": ctx.bot, "name": ctx.action, "status": true}),
        )
        .await?;
    let Some(doc) = found else {
        return Err(ActionError::failure(
            "No action found for given bot and name".to_string(),
        ));
    };
    Ok(doc
        .get("type")
        .and_then(|value| value.as_str())
        .unwrap_or("None")
        .to_string())
}

fn missing(key: &str) -> ActionError {
    ActionError::failure(format!("'{key}'"))
}

fn require<'a>(obj: &'a Map<String, Value>, key: &str) -> Result<&'a Value, ActionError> {
    obj.get(key).ok_or_else(|| missing(key))
}

fn as_object<'a>(value: &'a Value, key: &str) -> Result<&'a Map<String, Value>, ActionError> {
    value
        .as_object()
        .ok_or_else(|| ActionError::failure(format!("'{key}' is not an object")))
}

fn opt_string(value: Option<String>) -> Value {
    value.map(Value::String).unwrap_or(Value::Null)
}

fn text_of(tracker: &Tracker) -> Value {
    opt_string(tracker.user_text())
}

fn intent_of(tracker: &Tracker, skip_fallback: bool) -> Value {
    opt_string(tracker.intent(skip_fallback))
}

fn flag(value: Option<&Value>, default: bool) -> bool {
    match value {
        None => default,
        Some(item) => py_truthy(item),
    }
}

async fn load_one(
    store: &dyn ActionStore,
    collection: &str,
    filter: &Value,
    missing_message: &str,
) -> Result<Value, ActionError> {
    store
        .find_one(collection, filter)
        .await?
        .ok_or_else(|| ActionError::failure(missing_message.to_string()))
}

async fn save_log(store: &dyn ActionStore, doc: Value) -> Result<(), ActionError> {
    store.insert_one("action_server_logs", doc).await
}

fn status_json(status: Option<u16>) -> Value {
    status.map(|code| Value::from(code)).unwrap_or(Value::Null)
}

pub(super) fn py_type_name(value: &Value) -> &'static str {
    match value {
        Value::Null => "NoneType",
        Value::Bool(_) => "bool",
        Value::Number(number) if number.is_f64() => "float",
        Value::Number(_) => "int",
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
    }
}

pub(super) fn not_subscriptable(value: &Value) -> ActionError {
    ActionError::failure(format!(
        "'{}' object is not subscriptable",
        py_type_name(value)
    ))
}

pub(super) fn no_attribute(value: &Value, attr: &str) -> ActionError {
    ActionError::failure(format!(
        "'{}' object has no attribute '{attr}'",
        py_type_name(value)
    ))
}

pub(super) fn index<'a>(value: &'a Value, key: &str) -> Result<&'a Value, ActionError> {
    let Some(map) = value.as_object() else {
        return Err(not_subscriptable(value));
    };
    map.get(key).ok_or_else(|| missing(key))
}

/// Python `retrieve_value_for_custom_action_parameter`: a falsy param is None.
/// Otherwise the param is wrapped as a one-element list and resolved.
pub(super) fn custom_parameter(
    tracker_data: &Map<String, Value>,
    param: &Value,
    config: &Config,
) -> Result<Value, ActionError> {
    if !py_truthy(param) {
        return Ok(Value::Null);
    }
    if !param.is_object() {
        return Err(not_subscriptable(param));
    }
    let key = param
        .get("key")
        .and_then(|value| value.as_str())
        .ok_or_else(|| missing("key"))?
        .to_string();
    let wrapped = Value::Array(vec![param.clone()]);
    let (body, _) = prepare_request(tracker_data, Some(&wrapped), config)?;
    Ok(body.get(&key).cloned().unwrap_or(Value::Null))
}
