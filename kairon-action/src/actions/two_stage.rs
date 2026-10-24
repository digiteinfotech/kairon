use serde_json::{json, Map, Value};

use super::{index, intent_of, load_one, no_attribute, not_subscriptable, py_type_name, save_log, text_of};
use crate::context::{extract_nlu_text, note_failure_mail, py_log_str, trigger_info, ExecCtx};
use crate::error::ActionError;
use crate::pyfmt::{is_empty, py_str, py_truthy};

const UTTER_DEFAULT: &str = "utter_default";

pub async fn execute(ctx: &mut ExecCtx) -> Result<Map<String, Value>, ActionError> {
    let config = load_one(
        ctx.store.as_ref(),
        "kairon_two_stage_fallback_action",
        &json!({"bot": ctx.bot, "name": ctx.action, "status": true}),
        "Two stage fallback action config not found",
    )
    .await?;
    let text_recommendations = index(&config, "text_recommendations")?.clone();
    let trigger_rules = config.get("trigger_rules").cloned().unwrap_or(Value::Null);
    let latest_raw = ctx
        .tracker
        .latest_message
        .get("text")
        .cloned()
        .unwrap_or(Value::Null);
    let mut recommendations = Vec::new();
    let mut exception = Value::Null;

    if py_truthy(&text_recommendations) {
        let spec = text_recommendations
            .as_object()
            .ok_or_else(|| no_attribute(&text_recommendations, "get"))?;
        let count = spec.get("count").cloned().unwrap_or(Value::Null);
        if py_truthy(&count) {
            if spec.get("use_intent_ranking").map(py_truthy).unwrap_or(false) {
                let ranking = ctx
                    .tracker
                    .latest_message
                    .get("intent_ranking")
                    .cloned()
                    .unwrap_or(Value::Null);
                let sliced = slice_ranking(&ranking, &count)?;
                for intent in sliced {
                    match training_button(ctx, &intent).await {
                        Ok(button) => recommendations.push(button),
                        Err(err) => exception = Value::String(err.to_string()),
                    }
                }
            } else {
                let query = latest_raw.as_str().ok_or_else(|| {
                    ActionError::failure("search text must be a string".to_string())
                })?;
                let limit = count_limit(&count)?;
                let found = ctx
                    .store
                    .text_search(
                        "training_examples",
                        query,
                        &json!({"bot": ctx.bot, "status": true}),
                        limit,
                    )
                    .await?;
                for result in found {
                    let text = result.get("text").cloned().unwrap_or(Value::Null);
                    recommendations.push(json!({"text": text.clone(), "payload": text}));
                }
            }
        }
    }

    if py_truthy(&trigger_rules) {
        let rules = trigger_rules.as_array().ok_or_else(|| no_attribute(&trigger_rules, "get"))?;
        for rule in rules {
            recommendations.push(rule_button(rule, &latest_raw)?);
        }
    }

    if recommendations.is_empty() {
        ctx.dispatcher.utter_response(UTTER_DEFAULT);
    } else {
        let text = config.get("fallback_message").cloned().unwrap_or(Value::Null);
        ctx.dispatcher
            .utter_buttons(text, Value::Array(recommendations.clone()));
    }

    let doc = json!({
        "type": "two_stage_fallback",
        "intent": intent_of(&ctx.tracker, false),
        "action": ctx.action,
        "sender": ctx.tracker.sender_id,
        "bot": ctx.tracker.get_slot("bot"),
        "exception": exception,
        "bot_response": py_log_str(&Value::Array(recommendations)),
        "status": "Success",
        "user_msg": text_of(&ctx.tracker),
        "trigger_info": trigger_info(&ctx.action_call),
        "request_id": ctx.request_id,
    });
    if let Err(err) = save_log(ctx.store.as_ref(), doc).await {
        note_failure_mail(&ctx.bot, &ctx.action, ctx.tracker.user_text().as_deref());
        return Err(err);
    }
    Ok(Map::new())
}

async fn training_button(ctx: &ExecCtx, intent: &Value) -> Result<Value, ActionError> {
    let name = index(intent, "name")?
        .as_str()
        .ok_or_else(|| not_subscriptable(intent))?
        .to_string();
    let pattern = format!("^{}$", regex::escape(&name));
    let docs = ctx
        .store
        .find_many(
            "training_examples",
            &json!({
                "bot": ctx.bot,
                "status": true,
                "intent": {"$regex": pattern, "$options": "i"}
            }),
            Some(1),
            Some("timestamp"),
        )
        .await?;
    let Some(example) = docs.into_iter().next() else {
        return Err(ActionError::failure(String::new()));
    };
    let text = index(&example, "text")?
        .as_str()
        .ok_or_else(|| not_subscriptable(&example))?;
    let text = extract_nlu_text(text);
    Ok(json!({"text": text, "payload": text}))
}

fn rule_button(rule: &Value, latest: &Value) -> Result<Value, ActionError> {
    if !rule.is_object() {
        return Err(no_attribute(rule, "get"));
    }
    let dynamic = rule.get("is_dynamic_msg").map(py_truthy).unwrap_or(false);
    let payload = py_str(index(rule, "payload")?);
    let payload = if dynamic {
        format!(
            "/{payload}{{\"kairon_user_msg\": \"{}\"}}",
            py_str(latest)
        )
    } else if !is_empty(rule.get("message").unwrap_or(&Value::Null)) {
        format!(
            "/{payload}{{\"kairon_user_msg\": \"{}\"}}",
            py_str(rule.get("message").unwrap_or(&Value::Null))
        )
    } else {
        format!("/{payload}")
    };
    let text = index(rule, "text")?.clone();
    let mut button = Map::new();
    button.insert("payload".into(), Value::String(payload));
    button.insert("text".into(), text);
    Ok(Value::Object(button))
}

fn count_limit(count: &Value) -> Result<i64, ActionError> {
    match count {
        Value::Bool(true) => Ok(1),
        Value::Number(number) if !number.is_f64() => Ok(number.as_i64().unwrap_or(i64::MAX)),
        other => Err(ActionError::failure(format!(
            "'{}' object cannot be interpreted as an integer",
            py_type_name(other)
        ))),
    }
}

enum SliceEnd {
    Index(i64),
    Float,
}

fn slice_ranking(ranking: &Value, count: &Value) -> Result<Vec<Value>, ActionError> {
    let end = match count {
        Value::Bool(true) => SliceEnd::Index(2),
        Value::Number(number) if number.is_f64() => SliceEnd::Float,
        Value::Number(number) => SliceEnd::Index(number.as_i64().unwrap_or(0).saturating_add(1)),
        Value::String(_) => {
            return Err(ActionError::failure(
                "unsupported operand type(s) for +: 'int' and 'str'".to_string(),
            ))
        }
        other => {
            return Err(ActionError::failure(format!(
                "unsupported operand type(s) for +: 'int' and '{}'",
                py_type_name(other)
            )))
        }
    };
    match ranking {
        Value::Null => Err(not_subscriptable(ranking)),
        Value::Object(_) => Err(ActionError::failure("unhashable type: 'slice'".to_string())),
        Value::Array(items) => match end {
            SliceEnd::Float => Err(ActionError::failure(
                "slice indices must be integers or None or have an __index__ method".to_string(),
            )),
            SliceEnd::Index(end) => Ok(slice_py(items, 1, end)),
        },
        other => Err(not_subscriptable(other)),
    }
}

fn slice_py(items: &[Value], start: i64, end: i64) -> Vec<Value> {
    let len = items.len() as i64;
    let mut start = if start < 0 { start + len } else { start };
    let mut end = if end < 0 { end + len } else { end };
    if start < 0 {
        start = 0;
    }
    if end < 0 {
        end = 0;
    }
    if start > len {
        start = len;
    }
    if end > len {
        end = len;
    }
    if end <= start {
        return Vec::new();
    }
    items[start as usize..end as usize].to_vec()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn slice_skips_the_first_intent() {
        let ranking = json!([{"name": "nlu_fallback"}, {"name": "greet"}, {"name": "bye"}]);
        let sliced = slice_ranking(&ranking, &json!(2)).unwrap();
        assert_eq!(sliced.len(), 2);
        assert_eq!(sliced[0]["name"], "greet");
    }

    #[test]
    fn float_end_on_none_is_not_subscriptable() {
        let err = slice_ranking(&Value::Null, &json!(1.0)).unwrap_err();
        assert_eq!(err.to_string(), "'NoneType' object is not subscriptable");
    }

    #[test]
    fn float_end_on_a_list_rejects_the_slice() {
        let err = slice_ranking(&json!([1]), &json!(1.0)).unwrap_err();
        assert_eq!(
            err.to_string(),
            "slice indices must be integers or None or have an __index__ method"
        );
    }

    #[test]
    fn string_count_fails_before_subscript() {
        let err = slice_ranking(&Value::Null, &json!("2")).unwrap_err();
        assert_eq!(
            err.to_string(),
            "unsupported operand type(s) for +: 'int' and 'str'"
        );
    }

    #[test]
    fn dict_ranking_is_an_unhashable_slice() {
        let err = slice_ranking(&json!({"a": 1}), &json!(1.0)).unwrap_err();
        assert_eq!(err.to_string(), "unhashable type: 'slice'");
    }
}
