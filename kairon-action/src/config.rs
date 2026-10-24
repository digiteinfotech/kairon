use serde_json::{Map, Value};
use std::env;
use std::fs;
use std::path::Path;

pub const SDK_VERSION_DEFAULT: &str = "3.13.0.dev1";
pub const FERNET_DEFAULT: &str = "gH8F9M-3GTxT1z-XyvJXZlCfxfbMuFr2HgXDHl7Xkuw=";
pub const AES_KEY_DEFAULT: &str = "3b1fbd562a0b5a29cc9a1b29b2c2d17a8a62b0d94f7637f1088e07fa1dbdcd14";
pub const AES_IV_DEFAULT: &str = "2f7b56a2c3e4d5f681d8ab92bc9d8f47";

#[derive(Clone, Debug)]
pub struct Config {
    pub database_url: String,
    pub database_name: String,
    pub host: String,
    pub port: u16,
    pub allowed_origins: Vec<String>,
    pub request_timeout_secs: u64,
    pub evaluator_url: String,
    pub pyscript_trigger_task: bool,
    pub pyscript_url: String,
    pub web_search_url: Option<String>,
    pub web_search_trigger_task: bool,
    pub fernet_key: String,
    pub rasa_sdk_version: String,
    pub callback_base_url: String,
    pub aes_key_hex: String,
    pub aes_iv_hex: String,
    pub frontend_url: String,
    pub unmasked_char_count: usize,
    pub unmasked_char_strategy: String,
}

impl Config {
    pub fn for_tests() -> Self {
        Self::from_env_and_yaml(&Map::new())
    }

    pub fn load() -> Self {
        let path = env::var("SYSTEM_FILE").unwrap_or_else(|_| "./system.yaml".to_string());
        let mut root = Map::new();
        if Path::new(&path).is_file() {
            match fs::read_to_string(&path) {
                Ok(text) => match serde_yaml::from_str::<Value>(&text) {
                    Ok(Value::Object(map)) => root = interpolate_map(map),
                    Ok(_) => tracing::warn!("system file {path} is not a mapping"),
                    Err(err) => tracing::warn!("failed to parse {path}: {err}"),
                },
                Err(err) => tracing::warn!("failed to read {path}: {err}"),
            }
        }
        Self::from_env_and_yaml(&root)
    }

    fn from_env_and_yaml(root: &Map<String, Value>) -> Self {
        let database_url = env_or(
            "DATABASE_URL",
            string_at(root, &["database", "url"])
                .unwrap_or_else(|| "mongodb://localhost:27017/conversations".to_string()),
        );
        let origins = env_origins().unwrap_or_else(|| {
            match dig(root, &["cors", "origin"]) {
                Some(Value::Array(items)) => items
                    .iter()
                    .filter_map(|item| item.as_str().map(str::to_string))
                    .collect(),
                Some(Value::String(text)) => vec![text.clone()],
                _ => vec!["*".to_string()],
            }
        });
        let timeout = env_u64("ACTION_SERVER_REQUEST_TIMEOUT")
            .or_else(|| u64_at(root, &["action", "request_timeout"]))
            .unwrap_or(60);
        Self {
            database_name: database_name(&database_url),
            database_url,
            host: env_or("ACTION_HOST", "0.0.0.0".to_string()),
            port: env_u64("ACTION_PORT").unwrap_or(5055) as u16,
            allowed_origins: if origins.is_empty() {
                vec!["*".to_string()]
            } else {
                origins
            },
            request_timeout_secs: timeout.max(1),
            evaluator_url: env_or(
                "EXPRESSION_EVALUATOR_ENDPOINT",
                string_at(root, &["evaluator", "url"])
                    .unwrap_or_else(|| "http://192.168.100.109:8085/evaluate".to_string()),
            ),
            pyscript_trigger_task: env_bool("PYSCRIPT_TRIGGER_TASK").unwrap_or_else(|| {
                bool_at(root, &["evaluator", "pyscript", "trigger_task"]).unwrap_or(false)
            }),
            pyscript_url: env_or(
                "TRIGGER_MAIN_PYSCRIPT_URL",
                string_at(root, &["async_callback_action", "pyscript", "url"]).unwrap_or_else(
                    || "http://localhost:5059/main_pyscript/execute-python".to_string(),
                ),
            ),
            web_search_url: env::var("WEB_SEARCH_URL").ok().or_else(|| {
                string_at(root, &["web_search", "url"]).filter(|text| !text.is_empty())
            }),
            web_search_trigger_task: env_bool("WEB_SEARCH_TRIGGER_TASK").unwrap_or_else(|| {
                bool_at(root, &["web_search", "trigger_task"]).unwrap_or(false)
            }),
            fernet_key: env_or(
                "FERNET_KEY",
                string_at(root, &["security", "fernet_key"])
                    .unwrap_or_else(|| FERNET_DEFAULT.to_string()),
            ),
            rasa_sdk_version: env_or("RASA_SDK_VERSION", SDK_VERSION_DEFAULT.to_string()),
            callback_base_url: env_or(
                "ASYNC_CALLBACK_ACTION_SERVER_URL",
                string_at(root, &["async_callback_action", "url"])
                    .unwrap_or_else(|| "http://localhost:5059/callback".to_string()),
            ),
            aes_key_hex: env_or(
                "ASYNC_CALLBACK_AES_KEY",
                string_at(root, &["async_callback_action", "short_secret", "aes_key"])
                    .unwrap_or_else(|| AES_KEY_DEFAULT.to_string()),
            ),
            aes_iv_hex: env_or(
                "ASYNC_CALLBACK_AES_IV",
                string_at(root, &["async_callback_action", "short_secret", "aes_iv"])
                    .unwrap_or_else(|| AES_IV_DEFAULT.to_string()),
            ),
            frontend_url: env_or(
                "FRONTEND_URL",
                string_at(root, &["app", "frontend_url"])
                    .unwrap_or_else(|| "http://localhost:3000".to_string()),
            ),
            unmasked_char_count: env_u64("SECRET_UNMASKED_CHAR_COUNT")
                .map(|n| n as usize)
                .or_else(|| u64_at(root, &["security", "unmasked_char_count"]).map(|n| n as usize))
                .unwrap_or(2),
            unmasked_char_strategy: env_or(
                "SECRET_UNMASKED_CHAR_STRATEGY",
                string_at(root, &["security", "unmasked_char_strategy"])
                    .unwrap_or_else(|| "from_right".to_string()),
            ),
        }
    }
}

pub fn database_name(url: &str) -> String {
    let without_query = url.split('?').next().unwrap_or(url);
    let rest = without_query
        .split_once("://")
        .map(|(_, rest)| rest)
        .unwrap_or(without_query);
    match rest.split_once('/') {
        Some((_, path)) if !path.is_empty() => path.trim_matches('/').to_string(),
        _ => "conversations".to_string(),
    }
}

fn env_or(name: &str, default: String) -> String {
    env::var(name).ok().filter(|v| !v.is_empty()).unwrap_or(default)
}

fn env_u64(name: &str) -> Option<u64> {
    env::var(name).ok().and_then(|text| text.parse().ok())
}

fn env_bool(name: &str) -> Option<bool> {
    env::var(name).ok().and_then(|text| parse_bool(&text))
}

fn env_origins() -> Option<Vec<String>> {
    let text = env::var("ALLOWED_ORIGIN").ok()?;
    let parsed = parse_scalar(&text);
    match parsed {
        Value::Array(items) => Some(
            items
                .iter()
                .filter_map(|item| item.as_str().map(str::to_string))
                .collect(),
        ),
        Value::String(value) => Some(vec![value]),
        _ => None,
    }
}

fn dig<'a>(root: &'a Map<String, Value>, path: &[&str]) -> Option<&'a Value> {
    let mut current = root.get(*path.first()?)?;
    for key in &path[1..] {
        current = current.as_object()?.get(*key)?;
    }
    Some(current)
}

fn string_at(root: &Map<String, Value>, path: &[&str]) -> Option<String> {
    match dig(root, path)? {
        Value::String(text) if !text.is_empty() => Some(text.clone()),
        Value::Number(number) => Some(number.to_string()),
        Value::Bool(flag) => Some(flag.to_string()),
        _ => None,
    }
}

fn u64_at(root: &Map<String, Value>, path: &[&str]) -> Option<u64> {
    match dig(root, path)? {
        Value::Number(number) => number.as_u64().or_else(|| number.as_i64().map(|n| n as u64)),
        Value::String(text) => text.parse().ok(),
        _ => None,
    }
}

fn bool_at(root: &Map<String, Value>, path: &[&str]) -> Option<bool> {
    match dig(root, path)? {
        Value::Bool(flag) => Some(*flag),
        Value::String(text) => parse_bool(text),
        _ => None,
    }
}

fn interpolate_map(map: Map<String, Value>) -> Map<String, Value> {
    map.into_iter()
        .map(|(key, value)| (key, interpolate_value(value)))
        .collect()
}

fn interpolate_value(value: Value) -> Value {
    match value {
        Value::String(text) => interpolate_string(&text),
        Value::Array(items) => Value::Array(items.into_iter().map(interpolate_value).collect()),
        Value::Object(map) => Value::Object(interpolate_map(map)),
        other => other,
    }
}

fn interpolate_string(text: &str) -> Value {
    let pattern = regex::Regex::new(r"\$\{([A-Za-z0-9_]+)(?::([^}]*))?\}").expect("regex");
    if let Some(caps) = pattern.captures(text) {
        if caps.get(0).map(|m| m.as_str()) == Some(text) {
            let name = caps.get(1).map(|m| m.as_str()).unwrap_or("");
            let default = caps.get(2).map(|m| m.as_str()).unwrap_or("");
            if let Ok(env_value) = env::var(name) {
                if !env_value.is_empty() {
                    return parse_scalar(&env_value);
                }
            }
            return parse_scalar(default);
        }
    }
    let replaced = pattern.replace_all(text, |caps: &regex::Captures| {
        let name = caps.get(1).map(|m| m.as_str()).unwrap_or("");
        let default = caps.get(2).map(|m| m.as_str()).unwrap_or("");
        if let Ok(env_value) = env::var(name) {
            if !env_value.is_empty() {
                return env_value;
            }
        }
        scalar_to_string(&parse_scalar(default))
    });
    Value::String(replaced.into_owned())
}

fn parse_scalar(raw: &str) -> Value {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return Value::String(String::new());
    }
    let unquoted = if (trimmed.starts_with('"') && trimmed.ends_with('"') && trimmed.len() >= 2)
        || (trimmed.starts_with('\'') && trimmed.ends_with('\'') && trimmed.len() >= 2)
    {
        &trimmed[1..trimmed.len() - 1]
    } else {
        trimmed
    };
    if unquoted != trimmed {
        return Value::String(unquoted.to_string());
    }
    if let Some(flag) = parse_bool(unquoted) {
        return Value::Bool(flag);
    }
    if let Ok(number) = unquoted.parse::<i64>() {
        return Value::Number(number.into());
    }
    if let Ok(number) = unquoted.parse::<f64>() {
        if let Some(number) = serde_json::Number::from_f64(number) {
            return Value::Number(number);
        }
    }
    if (unquoted.starts_with('[') && unquoted.ends_with(']'))
        || (unquoted.starts_with('{') && unquoted.ends_with('}'))
    {
        if let Ok(value) = serde_json::from_str::<Value>(unquoted) {
            return value;
        }
        if let Ok(value) = serde_yaml::from_str::<Value>(unquoted) {
            return value;
        }
    }
    Value::String(unquoted.to_string())
}

fn parse_bool(text: &str) -> Option<bool> {
    match text.to_ascii_lowercase().as_str() {
        "true" => Some(true),
        "false" => Some(false),
        _ => None,
    }
}

fn scalar_to_string(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        Value::Bool(flag) => flag.to_string(),
        Value::Number(number) => number.to_string(),
        Value::Null => String::new(),
        other => other.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn database_name_from_path() {
        assert_eq!(
            database_name("mongodb://localhost:27017/conversations"),
            "conversations"
        );
        assert_eq!(database_name("mongodb://mongo:27017/kairon"), "kairon");
        assert_eq!(database_name("mongodb://localhost:27017"), "conversations");
    }
}
