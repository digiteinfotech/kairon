use std::time::Duration;

use lettre::message::header::ContentType;
use lettre::message::Mailbox;
use lettre::transport::smtp::authentication::Credentials;
use lettre::{AsyncSmtpTransport, AsyncTransport, Message, Tokio1Executor};
use serde_json::{json, Map, Value};

use super::{custom_parameter, index, intent_of, load_one, save_log, text_of};
use crate::context::{build_context, note_failure_mail, trigger_info, ExecCtx, FAILURE_TEXT};
use crate::error::ActionError;
use crate::pyfmt::{html_escape, py_str, py_truthy};

pub async fn execute(ctx: &mut ExecCtx) -> Result<Map<String, Value>, ActionError> {
    let config = load_one(
        ctx.store.as_ref(),
        "email_action_config",
        &json!({"bot": ctx.bot, "action_name": ctx.action, "status": true}),
        "No Email action found for given action and bot",
    )
    .await?;
    let mut bot_response = config.get("response").cloned().unwrap_or(Value::Null);
    let dispatch = match config.get("dispatch_bot_response") {
        None => true,
        Some(value) => py_truthy(value),
    };
    let smtp_password = config.get("smtp_password").cloned().unwrap_or(Value::Null);
    let smtp_userid = config.get("smtp_userid").cloned().unwrap_or(Value::Null);
    let custom_text = config.get("custom_text").cloned().unwrap_or(Value::Null);
    let mut exception = Value::Null;
    let mut status = "Success".to_string();

    if let Err(err) = send_all(
        ctx,
        &config,
        &smtp_password,
        &smtp_userid,
        &custom_text,
    )
    .await
    {
        exception = Value::String(err.to_string());
        bot_response = Value::String(FAILURE_TEXT.to_string());
        status = "Failed".to_string();
        note_failure_mail(&ctx.bot, &ctx.action, ctx.tracker.user_text().as_deref());
    }

    if dispatch {
        ctx.dispatcher.utter_text(bot_response.clone());
    }
    let action_name = index(&config, "action_name")?.clone();
    let doc = json!({
        "type": "email_action",
        "intent": intent_of(&ctx.tracker, false),
        "action": action_name,
        "sender": ctx.tracker.sender_id,
        "bot": ctx.tracker.get_slot("bot"),
        "exception": exception,
        "bot_response": bot_response,
        "status": status,
        "user_msg": text_of(&ctx.tracker),
        "trigger_info": trigger_info(&ctx.action_call),
        "request_id": ctx.request_id,
    });
    save_log(ctx.store.as_ref(), doc).await?;
    let mut slots = Map::new();
    slots.insert("kairon_action_response".into(), bot_response);
    Ok(slots)
}

async fn send_all(
    ctx: &ExecCtx,
    config: &Value,
    smtp_password: &Value,
    smtp_userid: &Value,
    custom_text: &Value,
) -> Result<(), ActionError> {
    let (from_email, recipients) = email_ends(config, &ctx.tracker)?;
    let tracker_data = build_context(ctx.store.as_ref(), &ctx.tracker, &ctx.config, false).await?;
    let password = credential(&custom_parameter(&tracker_data, smtp_password, &ctx.config)?);
    let userid = credential(&custom_parameter(&tracker_data, smtp_userid, &ctx.config)?);
    for recipient in &recipients {
        let subject_text = py_str(index(config, "subject")?);
        let body = if py_truthy(custom_text) {
            let text = custom_parameter(&tracker_data, custom_text, &ctx.config)?;
            let rendered = py_str(&text);
            email_html(
                &subject_text,
                recipient,
                &rendered,
                &ctx.config.frontend_url,
            )
        } else {
            let conversation = conversation_text(tracker_data.get("chat_log"));
            email_html(
                &subject_text,
                recipient,
                &conversation,
                &ctx.config.frontend_url,
            )
        };
        let subject = format!("{} {}", ctx.tracker.sender_id, subject_text);
        let host = py_str(index(config, "smtp_url")?);
        let port = smtp_port(index(config, "smtp_port")?)?;
        let tls = py_truthy(index(config, "tls")?);
        deliver(
            &host,
            port,
            tls,
            &from_email,
            recipient,
            &subject,
            &body,
            &userid,
            &password,
        )
        .await?;
    }
    Ok(())
}

fn email_ends(config: &Value, tracker: &crate::tracker::Tracker) -> Result<(String, Vec<String>), ActionError> {
    let from_email = resolve_field(index(config, "from_email")?, tracker)?;
    let to_email = resolve_field(index(config, "to_email")?, tracker)?;
    let recipients = match &to_email {
        Value::String(text) => vec![text.clone()],
        Value::Array(items) => items.iter().map(py_str).collect(),
        _ => {
            return Err(ActionError::failure(
                "Invalid 'to_email' type. It must be of type str or list.".to_string(),
            ))
        }
    };
    let from_email = match from_email {
        Value::String(text) => text,
        _ => {
            return Err(ActionError::failure(
                "Invalid 'from_email' type. It must be of type str.".to_string(),
            ))
        }
    };
    Ok((from_email, recipients))
}

fn resolve_field(spec: &Value, tracker: &crate::tracker::Tracker) -> Result<Value, ActionError> {
    let kind = index(spec, "parameter_type")?;
    let raw = index(spec, "value")?.clone();
    if kind.as_str() == Some("slot") {
        let name = raw.as_str().unwrap_or("");
        Ok(tracker.get_slot(name))
    } else {
        Ok(raw)
    }
}

fn credential(value: &Value) -> String {
    if value.is_null() {
        String::new()
    } else {
        py_str(value)
    }
}

fn smtp_port(value: &Value) -> Result<u16, ActionError> {
    let number = match value {
        Value::Number(number) if number.is_f64() => number.as_f64().unwrap_or(0.0) as i64,
        Value::Number(number) => number.as_i64().or_else(|| number.as_u64().map(|n| n as i64)).unwrap_or(0),
        other => {
            return Err(ActionError::failure(format!(
                "invalid smtp port: {}",
                py_str(other)
            )))
        }
    };
    u16::try_from(number).map_err(|_| ActionError::failure(format!("invalid smtp port: {number}")))
}

fn conversation_text(chat_log: Option<&Value>) -> String {
    let Some(events) = chat_log.and_then(|value| value.as_array()) else {
        return String::new();
    };
    let mut lines = Vec::new();
    for event in events {
        let Some(obj) = event.as_object() else {
            continue;
        };
        let Some((key, value)) = obj.iter().next() else {
            continue;
        };
        let text = if key == "bot" {
            value.get("text").map(py_str).unwrap_or_default()
        } else {
            py_str(value)
        };
        lines.push(format!("{key}: {text}"));
    }
    lines.join("\n")
}

/// Stand-in for the email.yaml templates the Python server renders.
fn email_html(subject: &str, recipient: &str, body: &str, frontend: &str) -> String {
    format!(
        "<html><body><p>{}</p><p>To: {}</p><div>{}</div><p>{}</p></body></html>",
        html_escape(subject),
        html_escape(recipient),
        html_escape(body),
        html_escape(frontend)
    )
}

async fn deliver(
    host: &str,
    port: u16,
    tls: bool,
    from: &str,
    to: &str,
    subject: &str,
    html: &str,
    user: &str,
    password: &str,
) -> Result<(), ActionError> {
    let mailer = if tls {
        AsyncSmtpTransport::<Tokio1Executor>::starttls_relay(host)
            .map_err(|err| ActionError::failure(err.to_string()))?
            .port(port)
            .credentials(Credentials::new(user.to_string(), password.to_string()))
            .timeout(Some(Duration::from_secs(30)))
            .build()
    } else {
        AsyncSmtpTransport::<Tokio1Executor>::builder_dangerous(host)
            .port(port)
            .credentials(Credentials::new(user.to_string(), password.to_string()))
            .timeout(Some(Duration::from_secs(30)))
            .build()
    };
    let from_box: Mailbox = from
        .parse()
        .map_err(|err: lettre::address::AddressError| ActionError::failure(err.to_string()))?;
    let to_box: Mailbox = to
        .parse()
        .map_err(|err: lettre::address::AddressError| ActionError::failure(err.to_string()))?;
    let message = Message::builder()
        .from(from_box)
        .to(to_box)
        .subject(subject)
        .header(ContentType::TEXT_HTML)
        .body(html.to_string())
        .map_err(|err| ActionError::failure(err.to_string()))?;
    mailer
        .send(message)
        .await
        .map_err(|err| ActionError::failure(err.to_string()))?;
    Ok(())
}
