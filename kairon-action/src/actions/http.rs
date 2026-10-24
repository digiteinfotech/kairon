use serde_json::{json, Map, Value};

use super::{index, intent_of, load_one, not_subscriptable, save_log, status_json, text_of};
use crate::context::{
    build_context, compose_response, encrypt_secrets, evaluate_pyscript, execute_lenient,
    fill_slots, handle_utter, log_value, note_failure_mail, prepare_request, prepare_url,
    trigger_info, validate_status, ExecCtx, FAILURE_TEXT,
};
use crate::error::ActionError;
use crate::pyfmt::{is_empty, py_str, py_truthy};

struct HttpState {
    dispatch: bool,
    dispatch_raw: Value,
    dispatch_type: String,
    dispatch_type_raw: Value,
    bot_response: Value,
    response_log: Map<String, Value>,
    api_call_log: Map<String, Value>,
    parameter_log: Map<String, Value>,
    initial_slots: Map<String, Value>,
    final_slots: Map<String, Value>,
    http_response: Value,
    resp_status_code: Option<u16>,
    http_url: Value,
    request_method: Value,
    slot_values: Map<String, Value>,
    filled_slots: Map<String, Value>,
    time_elapsed: f64,
    time_slots: f64,
    time_pyscript: f64,
    time_compose: f64,
    exception: Value,
    status: String,
    set_slots: Value,
}

pub async fn execute(ctx: &mut ExecCtx) -> Result<Map<String, Value>, ActionError> {
    let mut state = HttpState {
        dispatch: true,
        dispatch_raw: Value::Bool(true),
        dispatch_type: "text".to_string(),
        dispatch_type_raw: Value::String("text".into()),
        bot_response: Value::Null,
        response_log: json_map(json!({"type": "response"})),
        api_call_log: json_map(json!({"type": "api_call"})),
        parameter_log: Map::new(),
        initial_slots: json_map(json!({"type": "slots"})),
        final_slots: json_map(json!({"type": "filled_slots"})),
        http_response: Value::Null,
        resp_status_code: None,
        http_url: Value::Null,
        request_method: Value::Null,
        slot_values: Map::new(),
        filled_slots: Map::new(),
        time_elapsed: 0.0,
        time_slots: 0.0,
        time_pyscript: 0.0,
        time_compose: 0.0,
        exception: Value::Null,
        status: "Success".to_string(),
        set_slots: Value::Null,
    };

    if let Err(err) = run_body(ctx, &mut state).await {
        let message = err.to_string();
        state.exception = Value::String(message.clone());
        state.status = "Failed".to_string();
        state
            .api_call_log
            .insert("exception".into(), Value::String(message));
        if !py_truthy(&state.bot_response) {
            state.bot_response = Value::String(FAILURE_TEXT.to_string());
        }
        state
            .response_log
            .insert("exception".into(), state.bot_response.clone());
        note_failure_mail(&ctx.bot, &ctx.action, ctx.tracker.user_text().as_deref());
    }

    if state.dispatch {
        let (parsed, message) =
            handle_utter(&mut ctx.dispatcher, &state.dispatch_type, &state.bot_response);
        state.bot_response = parsed;
        if let Some(message) = message {
            state
                .response_log
                .insert("message".into(), Value::String(message));
        }
    }
    let fail_reason = validate_status(&state.http_response, state.resp_status_code, false)?;
    let mut events = Vec::new();
    if state.initial_slots.contains_key("data") {
        events.push(Value::Object(state.initial_slots));
    }
    events.push(Value::Object(state.response_log));
    events.push(Value::Object(state.api_call_log));
    events.push(Value::Object(state.parameter_log));
    events.push(Value::Object(state.final_slots));
    let total = state.time_elapsed + state.time_slots + state.time_pyscript + state.time_compose;
    let doc = json!({
        "type": "http_action",
        "intent": intent_of(&ctx.tracker, false),
        "action": ctx.action,
        "sender": ctx.tracker.sender_id,
        "events": events,
        "url": state.http_url,
        "request_method": state.request_method,
        "bot_response": log_value(&state.bot_response),
        "fail_reason": fail_reason.map(Value::String).unwrap_or(Value::Null),
        "exception": state.exception,
        "bot": ctx.bot,
        "status": state.status,
        "user_msg": text_of(&ctx.tracker),
        "time_elapsed": elapsed_json(total),
        "http_status_code": status_json(state.resp_status_code),
        "trigger_info": trigger_info(&ctx.action_call),
        "request_id": ctx.request_id,
    });
    save_log(ctx.store.as_ref(), doc).await?;

    let mut filled = state.filled_slots;
    filled.insert("kairon_action_response".into(), state.bot_response);
    filled.insert("http_status_code".into(), status_json(state.resp_status_code));
    crate::context::map_update(&mut filled, state.slot_values);
    Ok(filled)
}

async fn run_body(ctx: &mut ExecCtx, state: &mut HttpState) -> Result<(), ActionError> {
    let config = load_one(
        ctx.store.as_ref(),
        "http_action_config",
        &json!({"bot": ctx.bot, "action_name": ctx.action, "status": true}),
        "No HTTP action found for given action and bot",
    )
    .await?;
    let response = index(&config, "response")?.clone();
    let dispatch = index(&response, "dispatch")?.clone();
    let dispatch_type = index(&response, "dispatch_type")?.clone();
    state.dispatch = py_truthy(&dispatch);
    state.dispatch_raw = dispatch;
    state.dispatch_type = dispatch_type.as_str().unwrap_or("").to_string();
    state.dispatch_type_raw = dispatch_type;
    let data = response.get("value").cloned().unwrap_or(Value::Null);
    let evaluation_type = response
        .get("evaluation_type")
        .cloned()
        .unwrap_or_else(|| Value::String("expression".into()));
    state.set_slots = index(&config, "set_slots")?.clone();
    if py_truthy(&state.set_slots) {
        if !state.set_slots.is_array() {
            return Err(not_subscriptable(&state.set_slots));
        }
        let slots = state.set_slots.as_array_mut().unwrap();
        for slot in slots.iter_mut() {
            let name = match index(slot, "name").map(|value| value.as_str().map(str::to_string)) {
                Ok(Some(name)) => name,
                Ok(None) => return Err(not_subscriptable(slot)),
                Err(err) => return Err(err),
            };
            let slot_value = ctx.tracker.get_slot(&name);
            let Some(obj) = slot.as_object_mut() else {
                return Err(not_subscriptable(slot));
            };
            obj.insert("slot_value".into(), slot_value);
        }
        state
            .initial_slots
            .insert("data".into(), state.set_slots.clone());
    }
    state.response_log.insert(
        "dispatch_bot_response".into(),
        state.dispatch_raw.clone(),
    );
    state
        .response_log
        .insert("dispatch_type".into(), state.dispatch_type_raw.clone());
    state.response_log.insert("data".into(), data);
    state
        .response_log
        .insert("evaluation_type".into(), evaluation_type);

    let mut tracker_data = build_context(ctx.store.as_ref(), &ctx.tracker, &ctx.config, true).await?;
    tracker_data.insert("bot".into(), Value::String(ctx.bot.clone()));
    let headers_cfg = config.get("headers");
    let (header_body, header_log) = prepare_request(&tracker_data, headers_cfg, &ctx.config)?;
    state
        .api_call_log
        .insert("headers".into(), Value::Object(header_log));

    let dynamic = config.get("dynamic_params").cloned().unwrap_or(Value::Null);
    let mut body = if !is_empty(&dynamic) {
        let script = dynamic.as_str().unwrap_or("");
        let (output, log, slots, elapsed) =
            evaluate_pyscript(&ctx.http, &ctx.config, script, &Value::Object(tracker_data.clone()))
                .await?;
        crate::context::map_update(&mut state.filled_slots, slots.clone());
        state.time_pyscript = elapsed;
        state.parameter_log.insert("type".into(), Value::String("dynamic_params".into()));
        state.parameter_log.insert("data".into(), dynamic);
        state.parameter_log.insert("response".into(), output.clone());
        state.parameter_log.insert("slots".into(), Value::Object(slots));
        state
            .parameter_log
            .insert("request_params".into(), Value::Array(log));
        state
            .parameter_log
            .insert("time_elapsed".into(), elapsed_json(elapsed));
        let masked = encrypt_secrets(&output, &tracker_data, &ctx.config);
        tracing::info!("request_body: {}", py_str(&masked));
        output
    } else {
        let params = index(&config, "params_list")?;
        let (body, log) = prepare_request(&tracker_data, Some(params), &ctx.config)?;
        state.parameter_log.insert("type".into(), Value::String("params_list".into()));
        state
            .parameter_log
            .insert("request_body".into(), Value::Object(body.clone()));
        let request_log = Value::Object(log);
        state
            .parameter_log
            .insert("request_params".into(), request_log.clone());
        let request_body = py_str(&request_log);
        tracing::info!("request_body: {}", request_body);
        Value::Object(body)
    };

    let request_method = index(&config, "request_method")?.clone();
    let http_url_raw = index(&config, "http_url")?
        .as_str()
        .unwrap_or("")
        .to_string();
    let http_url = prepare_url(&http_url_raw, &tracker_data);
    state.request_method = request_method.clone();
    state.http_url = Value::String(http_url.clone());

    let media = pop_media(&mut body)?;
    if py_truthy(&Value::Array(media)) {
        let _content_type = index(&config, "content_type")?;
        return Err(ActionError::failure(
            "media multipart is not available in this Rust server".to_string(),
        ));
    }
    let content_type = index(&config, "content_type")?
        .as_str()
        .unwrap_or("")
        .to_string();
    let method = request_method.as_str().unwrap_or("");
    let result = execute_lenient(
        &ctx.http,
        &ctx.config,
        method,
        &http_url,
        &body,
        &header_body,
        &content_type,
    )
    .await;
    state.time_elapsed = result.elapsed;
    state.http_response = result.body;
    state.resp_status_code = result.status;
    let response_headers = result.headers;
    let elapsed_logged = elapsed_json(if state.time_elapsed == 0.0 {
        0.0
    } else {
        state.time_elapsed
    });
    state
        .api_call_log
        .insert("method".into(), request_method);
    state
        .api_call_log
        .insert("url".into(), Value::String(http_url));
    state.api_call_log.insert("payload".into(), body);
    state
        .api_call_log
        .insert("response".into(), state.http_response.clone());
    state
        .api_call_log
        .insert("status_code".into(), status_json(state.resp_status_code));
    state
        .api_call_log
        .insert("time_elapsed".into(), elapsed_logged);
    state
        .api_call_log
        .insert("response_headers".into(), response_headers.clone());

    let response_context = json!({
        "data": state.http_response,
        "context": tracker_data,
        "http_status_code": status_json(state.resp_status_code),
        "response_headers": response_headers,
    });
    let (composed, compose_log, compose_time) =
        compose_response(&ctx.http, &ctx.config, &response, &response_context).await?;
    state.bot_response = composed.clone();
    state.time_compose = compose_time;
    state.response_log.insert("response".into(), composed);
    state.response_log.insert("bot_response_log".into(), compose_log);
    state
        .response_log
        .insert("time_elapsed".into(), elapsed_json(compose_time));

    let slots_for_fill = fill_list(&state.set_slots)?;
    let (values, slot_log, slot_time) =
        fill_slots(&ctx.http, &ctx.config, &slots_for_fill, &response_context).await;
    state.slot_values = values.clone();
    state.time_slots = slot_time;
    state.final_slots.insert("data".into(), Value::Object(values));
    state
        .final_slots
        .insert("slot_eval_log".into(), Value::Array(slot_log));
    state
        .final_slots
        .insert("time_elapsed".into(), elapsed_json(slot_time));
    Ok(())
}

fn pop_media(body: &mut Value) -> Result<Vec<Value>, ActionError> {
    let Some(obj) = body.as_object_mut() else {
        return Err(super::no_attribute(body, "pop"));
    };
    let media = obj.remove("media_ids").unwrap_or_else(|| json!([]));
    if let Value::Array(items) = media {
        Ok(items)
    } else {
        Ok(vec![media])
    }
}

fn fill_list(set_slots: &Value) -> Result<Vec<Value>, ActionError> {
    match set_slots {
        Value::Array(items) => Ok(items.clone()),
        Value::Null => Err(ActionError::failure(
            "'NoneType' object is not iterable".to_string(),
        )),
        other if matches!(other, Value::String(_) | Value::Object(_)) => Ok(vec![]),
        other => Err(ActionError::failure(format!(
            "'{}' object is not iterable",
            super::py_type_name(other)
        ))),
    }
}

fn elapsed_json(value: f64) -> Value {
    if value == 0.0 {
        Value::from(0_i64)
    } else {
        serde_json::Number::from_f64(value)
            .map(Value::Number)
            .unwrap_or_else(|| Value::from(0_i64))
    }
}

fn json_map(value: Value) -> Map<String, Value> {
    value.as_object().cloned().unwrap_or_default()
}
