//! Python `str`, `repr`, and `json.dumps` for logs and template substitution.

use serde_json::{Map, Number, Value};

pub fn py_truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(flag) => *flag,
        Value::Number(number) => number.as_f64().map(|n| n != 0.0).unwrap_or(true),
        Value::String(text) => !text.is_empty(),
        Value::Array(items) => !items.is_empty(),
        Value::Object(map) => !map.is_empty(),
    }
}

/// Python `ActionUtility.is_empty`: falsy values, plus whitespace-only strings.
/// Truthy non-strings are not empty (Python would call `.strip()` and throw).
pub fn is_empty(value: &Value) -> bool {
    match value {
        Value::Null => true,
        Value::Bool(flag) => !flag,
        Value::Number(number) => number.as_f64().map(|n| n == 0.0).unwrap_or(false),
        Value::String(text) => text.trim().is_empty(),
        Value::Array(items) => items.is_empty(),
        Value::Object(map) => map.is_empty(),
    }
}

pub fn check_empty_string(value: &Value) -> bool {
    match value {
        Value::Null => true,
        Value::String(text) => text.trim().is_empty(),
        other => is_empty(other),
    }
}

pub fn py_dumps(value: &Value) -> String {
    match value {
        Value::Null => "null".to_string(),
        Value::Bool(true) => "true".to_string(),
        Value::Bool(false) => "false".to_string(),
        Value::Number(number) => format_number(number),
        Value::String(text) => serde_json::to_string(text).unwrap_or_else(|_| "\"\"".to_string()),
        Value::Array(items) => {
            let parts: Vec<String> = items.iter().map(py_dumps).collect();
            format!("[{}]", parts.join(", "))
        }
        Value::Object(map) => {
            let parts: Vec<String> = map
                .iter()
                .map(|(key, item)| {
                    format!(
                        "{}: {}",
                        serde_json::to_string(key).unwrap_or_else(|_| "\"\"".to_string()),
                        py_dumps(item)
                    )
                })
                .collect();
            format!("{{{}}}", parts.join(", "))
        }
    }
}

pub fn py_str(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        other => py_repr(other),
    }
}

pub fn py_repr(value: &Value) -> String {
    match value {
        Value::Null => "None".to_string(),
        Value::Bool(true) => "True".to_string(),
        Value::Bool(false) => "False".to_string(),
        Value::Number(number) => format_number(number),
        Value::String(text) => py_repr_str(text),
        Value::Array(items) => {
            let parts: Vec<String> = items.iter().map(py_repr).collect();
            format!("[{}]", parts.join(", "))
        }
        Value::Object(map) => format!("{{{}}}", object_repr(map)),
    }
}

fn object_repr(map: &Map<String, Value>) -> String {
    let parts: Vec<String> = map
        .iter()
        .map(|(key, value)| format!("{}: {}", py_repr_str(key), py_repr(value)))
        .collect();
    parts.join(", ")
}

fn py_repr_str(text: &str) -> String {
    let mut out = String::from("'");
    for ch in text.chars() {
        match ch {
            '\\' => out.push_str("\\\\"),
            '\'' => out.push_str("\\'"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 32 => out.push_str(&format!("\\x{code:02x}", code = c as u32)),
            c => out.push(c),
        }
    }
    out.push('\'');
    out
}

fn format_number(number: &Number) -> String {
    if let Some(value) = number.as_i64() {
        return value.to_string();
    }
    if let Some(value) = number.as_u64() {
        return value.to_string();
    }
    if let Some(value) = number.as_f64() {
        if value.is_finite() && value.fract() == 0.0 && value.abs() < 1e15 {
            return format!("{value:.1}");
        }
        return format!("{value}");
    }
    number.to_string()
}

pub fn json_number_equal(left: &Value, right: &Value) -> bool {
    match (left, right) {
        (Value::Number(a), Value::Number(b)) => {
            a.as_f64().zip(b.as_f64()).map(|(x, y)| x == y).unwrap_or(false)
        }
        _ => left == right,
    }
}

pub fn html_escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn dumps_match_python_spacing() {
        let value = json!({"a": 1, "b": true, "c": null});
        assert_eq!(py_dumps(&value), r#"{"a": 1, "b": true, "c": null}"#);
    }

    #[test]
    fn str_and_repr_match_python() {
        assert_eq!(py_str(&Value::Null), "None");
        assert_eq!(py_str(&json!(true)), "True");
        assert_eq!(py_str(&json!(false)), "False");
        assert_eq!(py_str(&json!(1.5)), "1.5");
        assert_eq!(py_repr(&json!([1, "a"])), "[1, 'a']");
        assert_eq!(py_repr(&json!({"response": "name"})), "{'response': 'name'}");
        assert_eq!(py_str(&json!("hello")), "hello");
    }

    #[test]
    fn empty_versus_truthy() {
        assert!(is_empty(&json!("  ")));
        assert!(py_truthy(&json!("  ")));
        assert!(is_empty(&json!({})));
        assert!(!py_truthy(&json!({})));
        assert!(!is_empty(&json!(1)));
        assert!(is_empty(&json!(0)));
    }
}
