//! Tracker context, parameter binding, URL templates, and HTTP calls shared by actions.

use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use chrono::{TimeZone, Utc};
use regex::Regex;
use reqwest::header::{HeaderMap, HeaderName, HeaderValue};
use reqwest::Method;
use serde_json::{json, Map, Value};

use crate::config::Config;
use crate::crypto::{fernet_decrypt, fernet_encrypt};
use crate::error::ActionError;
use crate::pyfmt::{check_empty_string, is_empty, py_dumps, py_repr, py_str, py_truthy};
use crate::store::ActionStore;
use crate::tracker::{Dispatcher, Tracker, USER_MSG_ENTITY};

pub const FAILURE_TEXT: &str = "I have failed to process your request";
pub const CALLBACK_FAILURE_TEXT: &str = "Sorry, I am unable to process your request at the moment.";

pub struct ExecCtx {
    pub store: Arc<dyn ActionStore>,
    pub http: reqwest::Client,
    pub config: Arc<Config>,
    pub tracker: Tracker,
    pub domain: Value,
    pub action_call: Value,
    pub dispatcher: Dispatcher,
    pub request_id: String,
    pub bot: String,
    pub action: String,
}

#[derive(Clone, Debug)]
pub struct HttpResult {
    pub body: Value,
    pub status: Option<u16>,
    pub elapsed: f64,
    pub headers: Value,
}

pub async fn build_context(
    store: &dyn ActionStore,
    tracker: &Tracker,
    config: &Config,
    key_vault: bool,
) -> Result<Map<String, Value>, ActionError> {
    let (session_started, chat_log) = message_trail(&tracker.events);
    let secrets = if key_vault {
        load_key_vault(store, &tracker.get_slot("bot"), config).await?
    } else {
        Map::new()
    };
    let mut ctx = Map::new();
    ctx.insert("sender_id".into(), Value::String(tracker.sender_id.clone()));
    ctx.insert(
        "user_message".into(),
        tracker
            .user_text()
            .map(Value::String)
            .unwrap_or(Value::Null),
    );
    ctx.insert("slot".into(), Value::Object(tracker.current_slots()));
    ctx.insert(
        "intent".into(),
        tracker
            .intent(true)
            .map(Value::String)
            .unwrap_or(Value::Null),
    );
    ctx.insert("chat_log".into(), Value::Array(chat_log));
    ctx.insert("key_vault".into(), Value::Object(secrets));
    ctx.insert("latest_message".into(), tracker.latest_message.clone());
    ctx.insert(
        USER_MSG_ENTITY.into(),
        tracker
            .latest_entity(USER_MSG_ENTITY)
            .map(Value::String)
            .unwrap_or(Value::Null),
    );
    ctx.insert(
        "session_started".into(),
        session_started.map(Value::String).unwrap_or(Value::Null),
    );
    Ok(ctx)
}

fn message_trail(events: &[Value]) -> (Option<String>, Vec<Value>) {
    let mut initiated = None;
    let mut trail = Vec::new();
    for event in events {
        match event.get("event").and_then(|v| v.as_str()) {
            Some("session_started") => {
                if let Some(ts) = event.get("timestamp").and_then(|v| v.as_f64()) {
                    initiated = Some(format_unix(ts));
                }
            }
            Some("bot") => {
                let mut data = Map::new();
                data.insert(
                    "text".into(),
                    event.get("text").cloned().unwrap_or(Value::Null),
                );
                if let Some(Value::Object(extra)) = event.get("data") {
                    for (key, value) in extra {
                        data.insert(key.clone(), value.clone());
                    }
                }
                trail.push(json!({"bot": data}));
            }
            Some("user") => {
                trail.push(json!({"user": event.get("text").cloned().unwrap_or(Value::Null)}));
            }
            _ => {}
        }
    }
    (initiated, trail)
}

fn format_unix(ts: f64) -> String {
    Utc.timestamp_opt(ts as i64, 0)
        .single()
        .map(|dt| dt.format("%Y-%m-%d %H:%M:%S").to_string())
        .unwrap_or_default()
}

async fn load_key_vault(
    store: &dyn ActionStore,
    bot: &Value,
    config: &Config,
) -> Result<Map<String, Value>, ActionError> {
    let bot_id = bot.as_str().unwrap_or("");
    if bot_id.is_empty() {
        return Ok(Map::new());
    }
    let docs = store
        .find_many("key_vault", &json!({"bot": bot_id}), None, None)
        .await?;
    let mut secrets = Map::new();
    for doc in docs {
        let Some(key) = doc.get("key").and_then(|v| v.as_str()) else {
            continue;
        };
        let value = doc.get("value").cloned().unwrap_or(Value::Null);
        let plain = match value.as_str() {
            Some(text) if !text.trim().is_empty() => {
                Value::String(fernet_decrypt(text, &config.fernet_key).map_err(ActionError::failure)?)
            }
            _ => value,
        };
        secrets.insert(key.to_string(), plain);
    }
    Ok(secrets)
}

pub fn prepare_request(
    tracker_data: &Map<String, Value>,
    params: Option<&Value>,
    config: &Config,
) -> Result<(Map<String, Value>, Map<String, Value>), ActionError> {
    let mut body = Map::new();
    let mut log = Map::new();
    let list = match params {
        None | Some(Value::Null) => return Ok((body, log)),
        Some(Value::Array(items)) => items,
        Some(_) => {
            return Err(ActionError::failure(
                "action parameters must be a list".to_string(),
            ))
        }
    };
    for param in list {
        let Some(param) = param.as_object() else {
            continue;
        };
        let key = param
            .get("key")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let (value, log_value) = parameter_value(tracker_data, param, config)?;
        body.insert(key.clone(), value);
        log.insert(key, log_value);
    }
    Ok((body, log))
}

pub fn prepare_request_with_bot(
    tracker_data: &Map<String, Value>,
    params: Option<&Value>,
    bot: &str,
    config: &Config,
) -> Result<(Map<String, Value>, Value), ActionError> {
    let (mut body, log) = prepare_request(tracker_data, params, config)?;
    body.insert("bot".into(), Value::String(bot.to_string()));
    Ok((body, Value::Object(log)))
}

pub fn parameter_value(
    tracker_data: &Map<String, Value>,
    param: &Map<String, Value>,
    config: &Config,
) -> Result<(Value, Value), ActionError> {
    let kind = param
        .get("parameter_type")
        .and_then(|v| v.as_str())
        .unwrap_or("value");
    let mut value = match kind {
        "sender_id" => tracker_data
            .get("sender_id")
            .cloned()
            .unwrap_or(Value::Null),
        "slot" => {
            let name = param.get("value").and_then(|v| v.as_str()).unwrap_or("");
            tracker_data
                .get("slot")
                .and_then(|s| s.get(name))
                .cloned()
                .unwrap_or(Value::Null)
        }
        "user_message" => {
            let mut text = tracker_data
                .get("user_message")
                .cloned()
                .unwrap_or(Value::Null);
            if let Some(raw) = text.as_str() {
                if !is_empty(&text) && raw.starts_with('/') {
                    if let Some(entity) = tracker_data.get(USER_MSG_ENTITY) {
                        if !is_empty(entity) {
                            text = entity.clone();
                        }
                    }
                }
            }
            text
        }
        "intent" => tracker_data.get("intent").cloned().unwrap_or(Value::Null),
        "chat_log" => json!({
            "sender_id": tracker_data.get("sender_id").cloned().unwrap_or(Value::Null),
            "session_started": tracker_data.get("session_started").cloned().unwrap_or(Value::Null),
            "conversation": tracker_data.get("chat_log").cloned().unwrap_or(Value::Null),
        }),
        "key_vault" => {
            let name = param.get("value").and_then(|v| v.as_str()).unwrap_or("");
            tracker_data
                .get("key_vault")
                .and_then(|vault| vault.get(name))
                .cloned()
                .unwrap_or(Value::Null)
        }
        _ => param.get("value").cloned().unwrap_or(Value::Null),
    };
    let mut log_value = value.clone();
    let encrypt = param.get("encrypt").and_then(|v| v.as_bool()).unwrap_or(false);
    if encrypt && kind != "chat_log" {
        if kind == "value" && !is_empty(&value) {
            if let Some(text) = value.as_str() {
                value = Value::String(fernet_decrypt(text, &config.fernet_key).map_err(ActionError::failure)?);
            }
        }
        if !is_empty(&value) {
            log_value = Value::String(mask_value(&py_str(&value), config));
        }
    }
    Ok((value, log_value))
}

pub fn mask_value(value: &str, config: &Config) -> String {
    if value.trim().is_empty() {
        return value.to_string();
    }
    if value.chars().count() <= 4 {
        return "*".repeat(value.chars().count());
    }
    let len = value.chars().count();
    let keep = config.unmasked_char_count.min(len);
    let mask = "*".repeat(len - keep);
    let chars: Vec<char> = value.chars().collect();
    match config.unmasked_char_strategy.as_str() {
        "from_left" => format!("{}{mask}", chars.iter().take(keep).collect::<String>()),
        "from_right" => format!("{mask}{}", chars.iter().skip(len - keep).collect::<String>()),
        _ => "*".repeat(len),
    }
}

pub fn encrypt_secrets(body: &Value, tracker_data: &Map<String, Value>, config: &Config) -> Value {
    let Some(map) = body.as_object() else {
        return Value::Null;
    };
    Value::Object(mask_nested(map, tracker_data, config))
}

fn mask_nested(map: &Map<String, Value>, tracker_data: &Map<String, Value>, config: &Config) -> Map<String, Value> {
    let vault = tracker_data.get("key_vault").and_then(|v| v.as_object());
    let mut out = Map::new();
    for (key, value) in map {
        let masked = if let Some(child) = value.as_object() {
            Value::Object(mask_nested(child, tracker_data, config))
        } else if let Some(text) = value.as_str() {
            let secret = vault
                .map(|vault| vault.values().any(|item| item.as_str() == Some(text)))
                .unwrap_or(false);
            if secret {
                Value::String(mask_value(text, config))
            } else {
                value.clone()
            }
        } else {
            value.clone()
        };
        out.insert(key.clone(), masked);
    }
    out
}

pub fn prepare_url(http_url: &str, tracker_data: &Map<String, Value>) -> String {
    let mut user_msg = tracker_data
        .get("user_message")
        .cloned()
        .unwrap_or(Value::Null);
    if let Some(raw) = user_msg.as_str() {
        if !is_empty(&user_msg) && raw.starts_with('/') {
            if let Some(entity) = tracker_data.get(USER_MSG_ENTITY) {
                if !is_empty(entity) {
                    user_msg = entity.clone();
                }
            }
        }
    }
    let sender = stringish(tracker_data.get("sender_id"));
    let intent = stringish(tracker_data.get("intent"));
    let user = stringish(Some(&user_msg));
    let mut url = http_url
        .replace("$SENDER_ID", &sender)
        .replace("$INTENT", &intent)
        .replace("$USER_MESSAGE", &user);
    let key_re = Regex::new(r"\$\$[A-Za-z0-9_]+").expect("regex");
    let vault_hits: Vec<String> = key_re
        .find_iter(&url)
        .map(|m| m.as_str().to_string())
        .collect();
    for token in vault_hits {
        let name = token.trim_start_matches("$$");
        let value = tracker_data
            .get("key_vault")
            .and_then(|v| v.get(name))
            .filter(|v| py_truthy(v));
        url = url.replace(&token, &stringish(value));
    }
    let slot_re = Regex::new(r"\$[A-Za-z0-9_]+").expect("regex");
    let slot_hits: Vec<String> = slot_re
        .find_iter(&url)
        .map(|m| m.as_str().to_string())
        .collect();
    for token in slot_hits {
        let name = token.trim_start_matches('$');
        let value = tracker_data
            .get("slot")
            .and_then(|v| v.get(name))
            .filter(|v| py_truthy(v));
        url = url.replace(&token, &stringish(value));
    }
    url
}

fn stringish(value: Option<&Value>) -> String {
    match value {
        None | Some(Value::Null) => String::new(),
        Some(Value::String(text)) => text.clone(),
        Some(other) if !py_truthy(other) => String::new(),
        Some(other) => py_str(other),
    }
}

pub async fn execute_lenient(
    http: &reqwest::Client,
    config: &Config,
    method: &str,
    url: &str,
    body: &Value,
    headers: &Map<String, Value>,
    content_type: &str,
) -> HttpResult {
    let started = Instant::now();
    match send(http, config, method, url, body, headers, content_type).await {
        Ok(result) => result,
        Err(err) => {
            tracing::error!("http action request failed: {err}");
            HttpResult {
                body: Value::Null,
                status: None,
                elapsed: started.elapsed().as_secs_f64(),
                headers: Value::Null,
            }
        }
    }
}

pub async fn execute_strict(
    http: &reqwest::Client,
    config: &Config,
    method: &str,
    url: &str,
    body: &Value,
    headers: &Map<String, Value>,
) -> Result<Value, ActionError> {
    let method_l = method.to_ascii_lowercase();
    if !matches!(method_l.as_str(), "get" | "post" | "put" | "delete") {
        return Err(ActionError::failure(
            "Failed to execute the url: Invalid request method!".to_string(),
        ));
    }
    match send(http, config, method, url, body, headers, "json").await {
        Ok(result) => {
            let code = result.status.unwrap_or(0);
            if !matches!(code, 200 | 201 | 202 | 204) {
                let text = if result.body.is_string() {
                    py_str(&result.body)
                } else {
                    result.body.to_string()
                };
                return Err(ActionError::failure(format!(
                    "Failed to execute the url: Got non-200 status code: {code} {text}"
                )));
            }
            Ok(result.body)
        }
        Err(err) => Err(ActionError::failure(format!(
            "Failed to execute the url: {err}"
        ))),
    }
}

async fn send(
    http: &reqwest::Client,
    config: &Config,
    method: &str,
    url: &str,
    body: &Value,
    headers: &Map<String, Value>,
    content_type: &str,
) -> Result<HttpResult, String> {
    let started = Instant::now();
    let method = Method::from_bytes(method.to_ascii_uppercase().as_bytes())
        .map_err(|_| format!("Invalid request method!"))?;
    let mut header_map = HeaderMap::new();
    for (key, value) in headers {
        if value.is_null() {
            continue;
        }
        if let (Ok(name), Ok(val)) = (
            HeaderName::try_from(key.as_str()),
            HeaderValue::from_str(&py_str(value)),
        ) {
            header_map.insert(name, val);
        }
    }
    let stamp = Utc::now().format("%Y-%m-%d %H:%M:%S").to_string();
    if let Ok(val) = HeaderValue::from_str(&stamp) {
        header_map.insert("x-timestamp", val);
    }
    let mut request = http
        .request(method.clone(), url)
        .headers(header_map)
        .timeout(Duration::from_secs(config.request_timeout_secs));
    if method == Method::GET {
        if let Some(map) = body.as_object() {
            if !map.is_empty() {
                let pairs: Vec<(String, String)> = map
                    .iter()
                    .map(|(key, value)| (key.clone(), py_str(value)))
                    .collect();
                request = request.query(&pairs);
            }
        }
    } else if content_type == "data" {
        let form = body.as_object().cloned().unwrap_or_default();
        let pairs: Vec<(String, String)> = form
            .iter()
            .map(|(key, value)| (key.clone(), py_str(value)))
            .collect();
        request = request.form(&pairs);
    } else {
        request = request.json(body);
    }
    let response = request.send().await.map_err(|err| err.to_string())?;
    let status = response.status().as_u16();
    let headers = header_json(response.headers());
    let text = response.text().await.map_err(|err| err.to_string())?;
    let parsed = serde_json::from_str::<Value>(&text).unwrap_or(Value::String(text));
    Ok(HttpResult {
        body: parsed,
        status: Some(status),
        elapsed: started.elapsed().as_secs_f64(),
        headers,
    })
}

fn header_json(headers: &HeaderMap) -> Value {
    let mut map = Map::new();
    for (name, value) in headers.iter() {
        let text = value.to_str().unwrap_or("").to_string();
        map.insert(name.as_str().to_string(), Value::String(text));
    }
    Value::Object(map)
}

pub fn validate_status(http_response: &Value, status: Option<u16>, raise: bool) -> Result<Option<String>, ActionError> {
    if let Some(code) = status {
        if code != 0 && !matches!(code, 200 | 201 | 202 | 204) {
            let reason = format!(
                "Got non-200 status code:{code} http_response:{}",
                py_str(http_response)
            );
            if raise {
                return Err(ActionError::failure(reason));
            }
            return Ok(Some(reason));
        }
    }
    Ok(None)
}

pub async fn compose_response(
    http: &reqwest::Client,
    config: &Config,
    response_config: &Value,
    http_response: &Value,
) -> Result<(Value, Value, f64), ActionError> {
    let value = response_config.get("value").cloned().unwrap_or(Value::Null);
    let evaluation = response_config
        .get("evaluation_type")
        .and_then(|v| v.as_str())
        .unwrap_or("expression");
    if check_empty_string(&value) {
        let log = json!([
            format!("evaluation_type: {evaluation}"),
            format!("data: {}", py_str(http_response)),
            "Skipping evaluation as value is empty"
        ]);
        return Ok((Value::Null, log, 0.0));
    }
    if evaluation == "script" {
        let script = value.as_str().unwrap_or("");
        let (output, log, _slots, elapsed) =
            evaluate_pyscript(http, config, script, http_response).await?;
        return Ok((output, Value::Array(log), elapsed));
    }
    let status = http_response
        .get("http_status_code")
        .and_then(|v| v.as_u64())
        .map(|n| n as u16);
    validate_status(http_response, status, true)?;
    let result = prepare_response(value.as_str().unwrap_or(""), http_response)?;
    let log = json!([
        format!("evaluation_type: {evaluation}"),
        format!("expression: {}", py_str(&value)),
        format!("data: {}", py_str(http_response)),
        format!("response: {}", py_str(&result)),
    ]);
    Ok((result, log, 0.0))
}

pub fn prepare_response(template: &str, http_response: &Value) -> Result<Value, ActionError> {
    let parsed = attach_response(template, http_response);
    let re = Regex::new(r"\$\{(.+?)\}").expect("regex");
    let keys: Vec<String> = re
        .captures_iter(&parsed)
        .filter_map(|cap| cap.get(1).map(|m| m.as_str().to_string()))
        .collect();
    if keys.is_empty() {
        if check_empty_string(&Value::String(template.to_string())) {
            return Ok(http_response.clone());
        }
        return Ok(Value::String(parsed));
    }
    if !http_response.is_object() && !http_response.is_array() {
        return Err(ActionError::failure(
            "Could not find value for keys in response".to_string(),
        ));
    }
    let mapping = retrieve_values(&keys, http_response)?;
    let mut output = parsed;
    for (key, value) in mapping {
        let replacement = if value.is_object() {
            py_dumps(&value)
        } else {
            py_str(&value)
        };
        output = output.replace(&key, &replacement);
    }
    Ok(Value::String(output))
}

fn attach_response(template: &str, http_response: &Value) -> String {
    if !template.contains("${RESPONSE}") {
        return template.to_string();
    }
    let data = if http_response.is_object() {
        http_response.get("data").cloned().unwrap_or(Value::Null)
    } else {
        http_response.clone()
    };
    template.replace("${RESPONSE}", &py_dumps(&data))
}

fn retrieve_values(keys: &[String], http_response: &Value) -> Result<Vec<(String, Value)>, ActionError> {
    let mut mapping = Vec::new();
    for key in keys {
        let mut region = http_response;
        for part in key.split('.') {
            region = if let Some(map) = region.as_object() {
                map.get(part).ok_or_else(|| {
                    ActionError::failure(format!(
                        "Unable to retrieve value for key from HTTP response: '{part}'"
                    ))
                })?
            } else if let Some(items) = region.as_array() {
                let index: usize = part.parse().map_err(|err| {
                    ActionError::failure(format!(
                        "Unable to retrieve value for key from HTTP response: {err}"
                    ))
                })?;
                items.get(index).ok_or_else(|| {
                    ActionError::failure(
                        "Unable to retrieve value for key from HTTP response: index".to_string(),
                    )
                })?
            } else {
                return Err(ActionError::failure(
                    "Unable to retrieve value for key from HTTP response: not a collection"
                        .to_string(),
                ));
            };
        }
        mapping.push((format!("${{{key}}}"), region.clone()));
    }
    Ok(mapping)
}

pub async fn fill_slots(
    http: &reqwest::Client,
    config: &Config,
    set_slots: &[Value],
    http_response: &Value,
) -> (Map<String, Value>, Vec<Value>, f64) {
    let mut values = Map::new();
    let mut log = vec![Value::String("initiating slot evaluation".into())];
    let mut elapsed = 0.0;
    for slot in set_slots {
        let name = slot
            .get("name")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        log.push(Value::String(format!("Slot: {name}")));
        match compose_response(http, config, slot, http_response).await {
            Ok((value, slot_log, time)) => {
                if let Some(items) = slot_log.as_array() {
                    log.extend(items.clone());
                }
                elapsed += time;
                values.insert(name, value);
            }
            Err(err) => {
                tracing::error!("slot evaluation failed: {err}");
                log.push(Value::String(format!("Evaluation error for {name}: {err}")));
                log.push(Value::String(format!("Slot {name} eventually set to None.")));
                values.insert(name, Value::Null);
            }
        }
    }
    (values, log, elapsed)
}

pub async fn evaluate_script(
    http: &reqwest::Client,
    config: &Config,
    script: &str,
    data: &Value,
) -> Result<(Value, Vec<Value>), ActionError> {
    let mut log = vec![
        Value::String("evaluation_type: script".into()),
        Value::String(format!("script: {script}")),
        Value::String(format!("data: {}", py_str(data))),
        Value::String("raise_err_on_failure: True".into()),
    ];
    let body = json!({"script": script, "data": data});
    let resp = execute_strict(http, config, "POST", &config.evaluator_url, &body, &Map::new()).await?;
    log.push(Value::String(format!("Evaluator response: {}", py_str(&resp))));
    if !resp.get("success").map(py_truthy).unwrap_or(false) {
        return Err(ActionError::failure(format!(
            "Expression evaluation failed: {}",
            py_str(&resp)
        )));
    }
    Ok((resp.get("data").cloned().unwrap_or(Value::Null), log))
}

pub async fn evaluate_pyscript(
    http: &reqwest::Client,
    config: &Config,
    script: &str,
    data: &Value,
) -> Result<(Value, Vec<Value>, Map<String, Value>, f64), ActionError> {
    let started = Instant::now();
    let log = vec![
        Value::String("evaluation_type: script".into()),
        Value::String(format!("script: {script}")),
        Value::String(format!("data: {}", py_str(data))),
        Value::String("raise_err_on_failure: True".into()),
    ];
    let context = if data.get("context").map(|v| v.is_object()).unwrap_or(false) {
        let mut ctx = data.get("context").cloned().unwrap_or(json!({}));
        if let Some(obj) = ctx.as_object_mut() {
            obj.insert("data".into(), data.get("data").cloned().unwrap_or(Value::Null));
            obj.insert(
                "response_headers".into(),
                data.get("response_headers").cloned().unwrap_or(Value::Null),
            );
            obj.insert(
                "http_status_code".into(),
                data.get("http_status_code").cloned().unwrap_or(Value::Null),
            );
        }
        ctx
    } else {
        data.clone()
    };
    let result = run_pyscript(http, config, script, &context).await?;
    let slots = filter_system_slots(result.get("slots"));
    let mut output = if result.get("bot_response").map(py_truthy).unwrap_or(false) {
        result.get("bot_response").cloned().unwrap_or(Value::Null)
    } else if result.get("body").map(py_truthy).unwrap_or(false) {
        result.get("body").cloned().unwrap_or(Value::Null)
    } else {
        json!({})
    };
    if result.get("media_ids").map(py_truthy).unwrap_or(false) {
        if let Some(obj) = output.as_object_mut() {
            obj.insert(
                "media_ids".into(),
                result.get("media_ids").cloned().unwrap_or(Value::Null),
            );
        }
    }
    Ok((output, log, slots, started.elapsed().as_secs_f64()))
}

pub async fn run_pyscript(
    http: &reqwest::Client,
    config: &Config,
    source_code: &str,
    context: &Value,
) -> Result<Value, ActionError> {
    if config.pyscript_trigger_task {
        return Err(ActionError::failure(
            "pyscript trigger_task is not available in this Rust server".to_string(),
        ));
    }
    let body = json!({"source_code": source_code, "predefined_objects": context});
    let mut headers = Map::new();
    headers.insert(
        "Content-Type".into(),
        Value::String("application/json".into()),
    );
    let resp = execute_strict(http, config, "POST", &config.pyscript_url, &body, &headers).await?;
    let code = resp.get("statusCode").and_then(|v| v.as_i64()).unwrap_or(0);
    if code != 200 {
        return Err(ActionError::failure(format!(
            "Pyscript evaluation failed: {}",
            py_str(&resp)
        )));
    }
    Ok(resp.get("body").cloned().unwrap_or(Value::Null))
}

fn filter_system_slots(slots: Option<&Value>) -> Map<String, Value> {
    let Some(map) = slots.and_then(|v| v.as_object()) else {
        return Map::new();
    };
    map.iter()
        .filter(|(key, _)| key.as_str() != "bot")
        .map(|(key, value)| (key.clone(), value.clone()))
        .collect()
}

pub fn handle_utter(dispatcher: &mut Dispatcher, dispatch_type: &str, bot_response: &Value) -> (Value, Option<String>) {
    if !py_truthy(bot_response) {
        return (bot_response.clone(), None);
    }
    if dispatch_type == "json" {
        handle_json(dispatcher, bot_response)
    } else {
        handle_text(dispatcher, bot_response);
        (bot_response.clone(), None)
    }
}

fn handle_text(dispatcher: &mut Dispatcher, bot_response: &Value) {
    if let Some(items) = bot_response.as_array() {
        for message in items {
            if message.is_object() {
                dispatcher.utter(None, None, None, Some(message.clone()), None, None, None);
            } else {
                dispatcher.utter_text(Value::String(py_str(message)));
            }
        }
    } else {
        dispatcher.utter_text(Value::String(py_str(bot_response)));
    }
}

fn handle_json(dispatcher: &mut Dispatcher, bot_response: &Value) -> (Value, Option<String>) {
    let parsed = if let Some(text) = bot_response.as_str() {
        match serde_json::from_str::<Value>(text) {
            Ok(value) => value,
            Err(err) => {
                let message = format!("Failed to convert http response to json: {err}");
                tracing::error!("{message}");
                dispatcher.utter_text(Value::String(py_str(bot_response)));
                return (bot_response.clone(), Some(message));
            }
        }
    } else {
        bot_response.clone()
    };
    dispatcher.utter(None, None, None, Some(parsed.clone()), None, None, None);
    (parsed, None)
}

pub fn format_search_result(results: &[Value]) -> String {
    let mut formatted = String::new();
    for result in results {
        let text = result.get("text").and_then(|v| v.as_str()).unwrap_or("");
        let link = result.get("link").and_then(|v| v.as_str()).unwrap_or("");
        let title = result.get("title").and_then(|v| v.as_str()).unwrap_or("");
        formatted.push_str(text);
        formatted.push_str("\nTo know more, please visit: <a href = \"");
        formatted.push_str(link);
        formatted.push_str("\" target=\"_blank\" >");
        formatted.push_str(title);
        formatted.push_str("</a>\n\n");
    }
    formatted.trim().to_string()
}

pub fn slash_user_message(tracker: &Tracker) -> Value {
    let mut latest = tracker
        .user_text()
        .map(Value::String)
        .unwrap_or(Value::Null);
    if let Some(text) = latest.as_str() {
        if !is_empty(&latest) && text.starts_with('/') {
            if let Some(entity) = tracker.latest_entity(USER_MSG_ENTITY) {
                if !entity.trim().is_empty() {
                    latest = Value::String(entity);
                }
            }
        }
    }
    latest
}

pub fn extract_nlu_text(text: &str) -> String {
    let re = Regex::new(r"\[([^\]]+)\](?:\([^)]*\)|\{[^}]*\})").expect("regex");
    re.replace_all(text, "$1").into_owned()
}

pub fn log_value(value: &Value) -> Value {
    if py_truthy(value) {
        Value::String(py_str(value))
    } else {
        Value::Null
    }
}

pub fn py_log_str(value: &Value) -> Value {
    Value::String(py_repr(value))
}

pub fn trigger_info(action_call: &Value) -> Value {
    let mut info = action_call
        .get("trigger_info")
        .cloned()
        .filter(|v| v.is_object())
        .unwrap_or_else(|| json!({}));
    if let Some(obj) = info.as_object_mut() {
        obj.entry("name".to_string()).or_insert(Value::String(String::new()));
        // TriggerInfo uses trigger_name in the summary. MongoEngine field names:
        // the Python constructor is TriggerInfo(**trigger_info_data) with defaults
        // trigger_name "", trigger_type "implicit", trigger_id "".
        obj.entry("trigger_name".to_string())
            .or_insert(Value::String(String::new()));
        obj.entry("trigger_type".to_string())
            .or_insert(Value::String("implicit".into()));
        obj.entry("trigger_id".to_string())
            .or_insert(Value::String(String::new()));
        obj.remove("name");
    }
    info
}

pub fn note_failure_mail(bot: &str, action: &str, user_msg: Option<&str>) {
    tracing::warn!(
        "action failure mail was not sent; SMTP failure mail is not available in this Rust server bot={bot} action={action} user_msg={}",
        user_msg.unwrap_or("")
    );
}

pub fn now_secs() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

pub fn map_update(dest: &mut Map<String, Value>, src: Map<String, Value>) {
    for (key, value) in src {
        dest.insert(key, value);
    }
}

pub fn header_map_from_prepare(prepared: Map<String, Value>) -> Map<String, Value> {
    prepared
}

pub fn fernet_encrypt_text(text: &str, config: &Config) -> Result<String, ActionError> {
    fernet_encrypt(text, &config.fernet_key).map_err(ActionError::failure)
}

pub fn fernet_decrypt_text(token: &str, config: &Config) -> Result<String, ActionError> {
    fernet_decrypt(token, &config.fernet_key).map_err(ActionError::failure)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn sample() -> Map<String, Value> {
        let mut ctx = Map::new();
        ctx.insert("sender_id".into(), json!("s1"));
        ctx.insert("user_message".into(), json!("/greet"));
        ctx.insert("intent".into(), json!("greet"));
        ctx.insert("slot".into(), json!({"city": "Pune"}));
        ctx.insert("key_vault".into(), json!({"TOKEN": "secret"}));
        ctx.insert(USER_MSG_ENTITY.into(), json!("hello there"));
        ctx
    }

    #[test]
    fn url_substitutes_vault_before_slots() {
        let url = prepare_url(
            "http://example/$SENDER_ID/$INTENT/$$TOKEN/$city/$USER_MESSAGE",
            &sample(),
        );
        assert_eq!(url, "http://example/s1/greet/secret/Pune/hello there");
    }

    #[test]
    fn response_template_uses_python_json() {
        let ctx = json!({"data": {"who": "Ada"}, "http_status_code": 200});
        let text = prepare_response("Hello ${data.who}", &ctx).unwrap();
        assert_eq!(text, "Hello Ada");
        let dumped = prepare_response("R ${RESPONSE}", &ctx).unwrap();
        assert_eq!(dumped, r#"R {"who": "Ada"}"#);
    }

    #[test]
    fn list_placeholder_uses_python_repr() {
        let ctx = json!({"items": [1, "a"]});
        let text = prepare_response("L ${items}", &ctx).unwrap();
        assert_eq!(text, "L [1, 'a']");
    }

    #[test]
    fn nlu_markdown_is_stripped() {
        assert_eq!(extract_nlu_text("book [pune](city) now"), "book pune now");
    }
}
