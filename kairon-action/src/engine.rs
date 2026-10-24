//! Webhook action dispatch. Mirrors `ActionHandler.process_actions` and
//! `ActionProcessor.__process_action`: a blank `next_action` is JSON null,
//! and every error raised by an action becomes an empty event list plus a
//! processor failure log. The dispatcher messages already uttered stay.

use std::sync::Arc;

use serde_json::{json, Value};

use crate::actions;
use crate::config::Config;
use crate::context::{note_failure_mail, ExecCtx};
use crate::error::ActionError;
use crate::pyfmt::{is_empty, py_str, py_truthy};
use crate::store::ActionStore;
use crate::tracker::{slot_events, Tracker};

/// Drop the last dotted segment. `3.13.0.dev1` and `3.13.0` do not match.
pub fn version_core(version: &str) -> Vec<&str> {
    let mut parts: Vec<&str> = version.split('.').collect();
    if !parts.is_empty() {
        parts.pop();
    }
    parts
}

/// Warn when the client SDK version is missing or its core differs. Never fails the call.
pub fn check_version(client: Option<&str>, sdk: &str) {
    match client {
        None => tracing::warn!("action client version missing; rasa sdk is {sdk}"),
        Some(client) if version_core(client) != version_core(sdk) => {
            tracing::warn!("action client version {client} is not compatible with rasa sdk {sdk}");
        }
        Some(_) => {}
    }
}

pub async fn process_actions(
    store: Arc<dyn ActionStore>,
    http: reqwest::Client,
    config: Arc<Config>,
    action_call: Value,
    request_id: String,
) -> Result<Option<Value>, ActionError> {
    match action_call.get("version") {
        None => check_version(None, &config.rasa_sdk_version),
        Some(Value::String(text)) => check_version(Some(text), &config.rasa_sdk_version),
        Some(_) => tracing::warn!(
            "action client version is not a string; rasa sdk is {}",
            config.rasa_sdk_version
        ),
    }

    let Some(action) = next_action_name(&action_call)? else {
        tracing::warn!("Received an action call without an action.");
        return Ok(None);
    };
    tracing::debug!("Received request to run '{action}'");

    let tracker_value = action_call.get("tracker").ok_or_else(|| {
        ActionError::failure("'tracker'")
    })?;
    if !tracker_value.is_object() {
        return Err(ActionError::failure(format!(
            "'{}' object is not subscriptable",
            py_type_name(tracker_value)
        )));
    }
    let tracker = Tracker::from_value(tracker_value);
    let domain = action_call
        .get("domain")
        .cloned()
        .unwrap_or_else(|| json!({}));

    let mut ctx = ExecCtx {
        store: store.clone(),
        http,
        config,
        tracker,
        domain,
        action_call,
        dispatcher: Default::default(),
        request_id,
        bot: String::new(),
        action: action.clone(),
    };

    let slots = match run_or_reject(&mut ctx).await {
        Ok(slots) => slots,
        Err(err) => {
            tracing::error!("action '{action}' failed: {err}");
            record_failure(&ctx, &err.to_string()).await?;
            return Ok(Some(response(Vec::new(), ctx.dispatcher.messages)));
        }
    };
    let events = if slots.is_empty() {
        Vec::new()
    } else {
        slot_events(&slots)
    };
    tracing::debug!("Finished running '{action}'");
    Ok(Some(response(events, ctx.dispatcher.messages)))
}

async fn run_or_reject(
    ctx: &mut ExecCtx,
) -> Result<serde_json::Map<String, Value>, ActionError> {
    let bot_slot = ctx.tracker.get_slot("bot");
    if is_empty(&bot_slot) || is_empty(&Value::String(ctx.action.clone())) {
        return Err(ActionError::failure(
            "Bot id and action name not found in slot".to_string(),
        ));
    }
    ctx.bot = if let Some(text) = bot_slot.as_str() {
        text.to_string()
    } else {
        py_str(&bot_slot)
    };
    actions::run(ctx).await
}

async fn record_failure(ctx: &ExecCtx, exception: &str) -> Result<(), ActionError> {
    let intent = ctx
        .tracker
        .intent(true)
        .map(Value::String)
        .unwrap_or(Value::Null);
    let doc = json!({
        "intent": intent,
        "action": ctx.action,
        "sender": ctx.tracker.sender_id,
        "exception": exception,
        "bot": ctx.tracker.get_slot("bot"),
        "status": "Failed",
        "request_id": ctx.request_id,
    });
    ctx.store.insert_one("action_server_logs", doc).await?;
    let bot_slot = ctx.tracker.get_slot("bot");
    let bot_name = bot_slot.as_str().unwrap_or("");
    note_failure_mail(bot_name, &ctx.action, ctx.tracker.user_text().as_deref());
    Ok(())
}

fn response(events: Vec<Value>, messages: Vec<Value>) -> Value {
    json!({
        "events": events,
        "responses": messages,
    })
}

/// Python `if action_name and action_name.strip()`. The returned name is not stripped.
fn next_action_name(call: &Value) -> Result<Option<String>, ActionError> {
    let Some(value) = call.get("next_action") else {
        return Ok(None);
    };
    if !py_truthy(value) {
        return Ok(None);
    }
    let Some(text) = value.as_str() else {
        return Err(ActionError::failure(format!(
            "'{}' object has no attribute 'strip'",
            py_type_name(value)
        )));
    };
    if text.trim().is_empty() {
        return Ok(None);
    }
    Ok(Some(text.to_string()))
}

fn py_type_name(value: &Value) -> &'static str {
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

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use serde_json::json;

    use super::{process_actions, version_core};
    use crate::config::Config;
    use crate::store::MemoryStore;

    #[test]
    fn version_core_drops_the_last_segment() {
        assert_eq!(version_core("3.13.0.dev1"), vec!["3", "13", "0"]);
        assert_eq!(version_core("3.13.0"), vec!["3", "13"]);
        assert_ne!(version_core("3.13.0.dev1"), version_core("3.13.0"));
    }

    #[tokio::test]
    async fn blank_next_action_does_not_read_the_tracker() {
        let store: Arc<dyn crate::store::ActionStore> = Arc::new(MemoryStore::new());
        let http = reqwest::Client::builder().build().expect("client");
        let result = process_actions(
            store,
            http,
            Arc::new(Config::for_tests()),
            json!({"next_action": "   "}),
            "rid".into(),
        )
        .await
        .expect("blank");
        assert!(result.is_none());
    }

    #[tokio::test]
    async fn missing_tracker_is_a_failure() {
        let store: Arc<dyn crate::store::ActionStore> = Arc::new(MemoryStore::new());
        let http = reqwest::Client::builder().build().expect("client");
        let err = process_actions(
            store,
            http,
            Arc::new(Config::for_tests()),
            json!({"next_action": "greet"}),
            "rid".into(),
        )
        .await
        .expect_err("tracker");
        assert_eq!(err.to_string(), "'tracker'");
    }

    #[tokio::test]
    async fn numeric_next_action_has_no_strip() {
        let store: Arc<dyn crate::store::ActionStore> = Arc::new(MemoryStore::new());
        let http = reqwest::Client::builder().build().expect("client");
        let err = process_actions(
            store,
            http,
            Arc::new(Config::for_tests()),
            json!({"next_action": 1}),
            "rid".into(),
        )
        .await
        .expect_err("strip");
        assert_eq!(err.to_string(), "'int' object has no attribute 'strip'");
    }
}
