use serde_json::{json, Map, Value};

use super::{intent_of, load_one, no_attribute, save_log, text_of};
use crate::context::{
    build_context, fernet_decrypt_text, fernet_encrypt_text, handle_utter, log_value,
    note_failure_mail, now_secs, prepare_request_with_bot, trigger_info, ExecCtx,
    CALLBACK_FAILURE_TEXT,
};
use crate::crypto::xor_encrypt;
use crate::error::ActionError;
use crate::pyfmt::{py_dumps, py_truthy};

pub async fn execute(ctx: &mut ExecCtx) -> Result<Map<String, Value>, ActionError> {
    let mut bot_response = Value::Null;
    let mut exception = Value::Null;
    let mut filled_slots = Map::new();
    let mut dispatch = true;
    let mut status = "Success".to_string();
    let mut messages = Vec::new();
    let mut callback_url = Value::Null;
    let mut metadata_log = Value::Array(Vec::new());
    let mut dynamic_url_slot_name = Value::Null;
    let mut identifier = Value::Null;

    if let Err(err) = run_body(
        ctx,
        &mut dispatch,
        &mut bot_response,
        &mut dynamic_url_slot_name,
        &mut metadata_log,
        &mut callback_url,
        &mut identifier,
        &mut filled_slots,
    )
    .await
    {
        exception = Value::String(err.to_string());
        status = "Failed".to_string();
        if !py_truthy(&bot_response) {
            bot_response = Value::String(CALLBACK_FAILURE_TEXT.to_string());
        }
        note_failure_mail(&ctx.bot, &ctx.action, ctx.tracker.user_text().as_deref());
    }

    if dispatch {
        if py_truthy(&bot_response) && py_truthy(&callback_url) {
            let Some(text) = bot_response.as_str() else {
                return Err(no_attribute(&bot_response, "replace"));
            };
            let url = callback_url.as_str().unwrap_or("");
            bot_response = Value::String(text.replace("{callback_url}", url));
        }
        let (parsed, message) = handle_utter(&mut ctx.dispatcher, "text", &bot_response);
        bot_response = parsed;
        if let Some(message) = message {
            messages.push(Value::String(message));
        }
    }

    let doc = json!({
        "type": "callback_action",
        "intent": intent_of(&ctx.tracker, false),
        "action": ctx.action,
        "sender": ctx.tracker.sender_id,
        "bot_response": log_value(&bot_response),
        "messages": messages,
        "exception": exception,
        "bot": ctx.bot,
        "status": status,
        "user_msg": text_of(&ctx.tracker),
        "callback_url": callback_url,
        "callback_url_slot": dynamic_url_slot_name,
        "identifier": identifier,
        "metadata": metadata_log,
        "trigger_info": trigger_info(&ctx.action_call),
        "request_id": ctx.request_id,
    });
    save_log(ctx.store.as_ref(), doc).await?;
    Ok(filled_slots)
}

async fn run_body(
    ctx: &mut ExecCtx,
    dispatch: &mut bool,
    bot_response: &mut Value,
    dynamic_url_slot_name: &mut Value,
    metadata_log: &mut Value,
    callback_url: &mut Value,
    identifier_out: &mut Value,
    filled_slots: &mut Map<String, Value>,
) -> Result<(), ActionError> {
    let config = load_one(
        ctx.store.as_ref(),
        "callback_action_config",
        &json!({"bot": ctx.bot, "name": ctx.action, "status": true}),
        "No Async Callback action found for given action and bot",
    )
    .await?;
    *dispatch = match config.get("dispatch_bot_response") {
        None => true,
        Some(value) => py_truthy(value),
    };
    *bot_response = config.get("bot_response").cloned().unwrap_or(Value::Null);
    *dynamic_url_slot_name = config
        .get("dynamic_url_slot_name")
        .cloned()
        .unwrap_or(Value::Null);
    let metadata_list = config
        .get("metadata_list")
        .cloned()
        .unwrap_or_else(|| json!([]));
    let callback_name = config.get("callback_name").cloned().unwrap_or(Value::Null);
    let channel_key = ctx.tracker.latest_input_channel();
    let channel = match channel_key.as_deref() {
        Some("TelegramHandler") => "telegram".to_string(),
        Some("facebook") => "messenger".to_string(),
        Some("instagram") => "instagram".to_string(),
        Some("whatsapp") => "whatsapp".to_string(),
        other => format!("unsupported ({})", other.unwrap_or("None")),
    };
    let mut tracker_data = build_context(ctx.store.as_ref(), &ctx.tracker, &ctx.config, true).await?;
    tracker_data.insert("bot".into(), Value::String(ctx.bot.clone()));
    let (metadata, log) = prepare_request_with_bot(
        &tracker_data,
        Some(&metadata_list),
        &ctx.bot,
        &ctx.config,
    )?;
    *metadata_log = log;
    let (url, identifier, standalone) = create_entry(
        ctx,
        &ctx.action,
        &callback_name,
        &ctx.bot,
        &ctx.tracker.sender_id,
        &channel,
        metadata,
    )
    .await?;
    *callback_url = Value::String(url.clone());
    *identifier_out = Value::String(identifier.clone());
    if let Some(slot_name) = dynamic_url_slot_name.as_str() {
        let value = if standalone { identifier } else { url };
        filled_slots.insert(slot_name.to_string(), Value::String(value));
    }
    Ok(())
}

async fn create_entry(
    ctx: &ExecCtx,
    name: &str,
    callback_name: &Value,
    bot: &str,
    sender_id: &str,
    channel: &str,
    metadata: Map<String, Value>,
) -> Result<(String, String, bool), ActionError> {
    nonempty(name)?;
    let callback_name = match callback_name {
        Value::String(text) if !text.is_empty() => text.clone(),
        _ => {
            return Err(ActionError::failure(
                "Value must be a non-empty string".to_string(),
            ))
        }
    };
    nonempty(bot)?;
    nonempty(sender_id)?;
    nonempty(channel)?;
    let (token, standalone) = auth_token(ctx, bot, &callback_name).await?;
    let identifier = uuid::Uuid::now_v7().simple().to_string();
    let mut callback_url = format!("{}/", ctx.config.callback_base_url);
    if standalone {
        callback_url.push_str(&format!("s/{token}"));
    } else {
        callback_url.push_str(&format!("d/{identifier}/{token}"));
    }
    let doc = json!({
        "action_name": name,
        "callback_name": callback_name,
        "bot": bot,
        "sender_id": sender_id,
        "channel": channel,
        "metadata": metadata,
        "identifier": identifier,
        "callback_url": callback_url,
        "timestamp": now_secs(),
        "is_valid": true,
    });
    ctx.store.insert_one("callback_data", doc).await?;
    Ok((callback_url, identifier, standalone))
}

async fn auth_token(ctx: &ExecCtx, bot: &str, name: &str) -> Result<(String, bool), ActionError> {
    let filter = json!({
        "bot": bot,
        "name": {"$regex": format!("^{}$", regex::escape(name)), "$options": "i"},
    });
    let Some(entry) = ctx.store.find_one("callback_config", &filter).await? else {
        return Err(ActionError::failure(format!(
            "Callback Configuration with name '{name}' does not exist!"
        )));
    };
    let stored_name = entry.get("name").and_then(|v| v.as_str()).unwrap_or(name);
    let secret_token = entry
        .get("validation_secret")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let validation_secret = fernet_decrypt_text(secret_token, &ctx.config)?;
    let expire_in = entry.get("expire_in").cloned().unwrap_or(Value::Null);
    let info = json!({
        "bot": entry.get("bot").cloned().unwrap_or(Value::String(bot.to_string())),
        "callback_name": stored_name,
        "validation_secret": validation_secret,
        "expire_in": expire_in,
    });
    let token = fernet_encrypt_text(&py_dumps(&info), &ctx.config)?;
    let standalone = entry.get("standalone").map(py_truthy).unwrap_or(false);
    if entry.get("shorten_token").map(py_truthy).unwrap_or(false) {
        ctx.store
            .update_one(
                "callback_config",
                &filter,
                &json!({"$set": {"token_value": token}}),
            )
            .await?;
        let hash = entry
            .get("token_hash")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let short = xor_encrypt(hash, &ctx.config.aes_key_hex, &ctx.config.aes_iv_hex)
            .map_err(ActionError::failure)?;
        Ok((short, standalone))
    } else {
        Ok((token, standalone))
    }
}

fn nonempty(value: &str) -> Result<(), ActionError> {
    if value.is_empty() {
        Err(ActionError::failure(
            "Value must be a non-empty string".to_string(),
        ))
    } else {
        Ok(())
    }
}
