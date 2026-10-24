use std::io::{Read, Write};
use std::net::TcpListener;
use std::sync::Arc;
use std::thread;

use actix_web::http::StatusCode;
use actix_web::test;
use kairon_action::{
    create_app, fernet_decrypt, fernet_encrypt, ActionStore, AppState, Config, MemoryStore,
};
use serde_json::{json, Value};

const PERMISSIONS_POLICY: &str = "accelerometer=(), autoplay=(), camera=(), document-domain=(), encrypted-media=(), fullscreen=(), vibrate=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), picture-in-picture=(), sync-xhr=(), usb=()";

fn memory() -> (AppState, Arc<MemoryStore>) {
    AppState::memory(Config::for_tests())
}

fn tracker(bot: &str, sender: &str) -> Value {
    json!({
        "sender_id": sender,
        "slots": {"bot": bot},
        "latest_message": {"text": "hi", "intent": {"name": "greet"}},
        "events": []
    })
}

macro_rules! call {
    ($app:expr, $req:expr $(,)?) => {
        async {
            let response = test::call_service(&$app, $req.to_request()).await;
            let status = response.status();
            let headers = response.headers().clone();
            let bytes = test::read_body(response).await;
            let body = serde_json::from_slice::<Value>(&bytes).unwrap_or(Value::Null);
            (status, body, headers)
        }
    };
}

#[actix_web::test]
async fn index_and_health_are_up() {
    let (state, _) = memory();
    let app = test::init_service(create_app(state)).await;
    let (status, body, _) = call!(app, test::TestRequest::get().uri("/")).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["message"], "Kairon Action Server Up and Running");
    let (status, body, _) = call!(app, test::TestRequest::get().uri("/healthcheck")).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["message"], "health check ok");
}

#[actix_web::test]
async fn security_headers_and_request_id() {
    let (state, _) = memory();
    let app = test::init_service(create_app(state)).await;
    let response = test::call_service(
        &app,
        test::TestRequest::get()
            .uri("/")
            .insert_header(("X-Kairon-Request-ID", "req-9"))
            .insert_header(("Origin", "https://app.example"))
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    let headers = response.headers();
    assert_eq!(
        headers.get("permissions-policy").and_then(|v| v.to_str().ok()),
        Some(PERMISSIONS_POLICY)
    );
    assert_eq!(
        headers.get("x-kairon-request-id").and_then(|v| v.to_str().ok()),
        Some("req-9")
    );
    assert_eq!(
        headers
            .get("strict-transport-security")
            .and_then(|v| v.to_str().ok()),
        Some("max-age=31536000; includeSubDomains; preload")
    );
    assert_eq!(
        headers.get("referrer-policy").and_then(|v| v.to_str().ok()),
        Some("no-referrer")
    );
    assert!(headers
        .get("content-security-policy")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .contains("default-src 'self'"));
    assert_eq!(
        headers.get("cache-control").and_then(|v| v.to_str().ok()),
        Some("must-revalidate")
    );
    assert_eq!(
        headers
            .get("x-content-type-options")
            .and_then(|v| v.to_str().ok()),
        Some("nosniff")
    );
    assert_eq!(headers.get("server").and_then(|v| v.to_str().ok()), Some("Secure"));
    assert_eq!(
        headers
            .get("cross-origin-embedder-policy")
            .and_then(|v| v.to_str().ok()),
        Some("require-corp")
    );
    assert_eq!(
        headers
            .get("cross-origin-opener-policy")
            .and_then(|v| v.to_str().ok()),
        Some("same-origin")
    );
    assert_eq!(
        headers
            .get("cross-origin-resource-policy")
            .and_then(|v| v.to_str().ok()),
        Some("same-origin")
    );
    assert_eq!(
        headers
            .get("access-control-allow-origin")
            .and_then(|v| v.to_str().ok()),
        Some("https://app.example")
    );
    assert_eq!(
        headers
            .get("access-control-allow-credentials")
            .and_then(|v| v.to_str().ok()),
        Some("true")
    );
    assert_eq!(
        headers
            .get("access-control-expose-headers")
            .and_then(|v| v.to_str().ok()),
        Some("content-disposition")
    );

    let plain = test::call_service(&app, test::TestRequest::get().uri("/").to_request()).await;
    assert_eq!(
        plain
            .headers()
            .get("access-control-allow-origin")
            .and_then(|v| v.to_str().ok()),
        Some("*")
    );
    assert!(plain
        .headers()
        .get("x-kairon-request-id")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .len()
        > 8);
}

#[actix_web::test]
async fn unknown_path_is_json_404() {
    let (state, _) = memory();
    let app = test::init_service(create_app(state)).await;
    let (status, body, _) = call!(app, test::TestRequest::get().uri("/missing")).await;
    assert_eq!(status, StatusCode::NOT_FOUND);
    assert_eq!(body["success"], false);
    assert_eq!(body["error_code"], 404);
    assert_eq!(body["message"], "Not Found");
    assert_eq!(body["data"], Value::Null);
}

#[actix_web::test]
async fn invalid_json_is_422() {
    let (state, _) = memory();
    let app = test::init_service(create_app(state)).await;
    let response = test::call_service(
        &app,
        test::TestRequest::post()
            .uri("/webhook")
            .set_payload("not-json")
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
    let body: Value = test::read_body_json(response).await;
    assert_eq!(body["success"], false);
    assert_eq!(body["error_code"], 422);
    assert_eq!(body["data"], Value::Null);

    let response = test::call_service(
        &app,
        test::TestRequest::post()
            .uri("/webhook")
            .set_payload("[1]")
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
}

#[actix_web::test]
async fn blank_next_action_is_json_null_without_a_tracker() {
    let (state, _) = memory();
    let app = test::init_service(create_app(state)).await;
    let response = test::call_service(
        &app,
        test::TestRequest::post()
            .uri("/webhook")
            .set_json(json!({"next_action": "  "}))
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    let bytes = test::read_body(response).await;
    assert_eq!(bytes.as_ref(), b"null");
}

#[actix_web::test]
async fn missing_tracker_is_500() {
    let (state, _) = memory();
    let app = test::init_service(create_app(state)).await;
    let (status, body, _) = call!(
        app,
        test::TestRequest::post()
            .uri("/webhook")
            .set_json(json!({"next_action": "greet"})),
    )
    .await;
    assert_eq!(status, StatusCode::INTERNAL_SERVER_ERROR);
    assert_eq!(body["success"], false);
    assert_eq!(body["error_code"], 500);
    assert_eq!(body["message"], "'tracker'");
    assert_eq!(body["data"], Value::Null);
}

#[actix_web::test]
async fn missing_bot_slot_logs_a_processor_failure() {
    let (state, store) = memory();
    let app = test::init_service(create_app(state)).await;
    let (status, body, _) = call!(
        app,
        test::TestRequest::post()
            .uri("/webhook")
            .insert_header(("X-Kairon-Request-ID", "bot-missing"))
            .set_json(json!({
                "next_action": "anything",
                "tracker": {"sender_id": "s1", "slots": {}}
            })),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["events"], json!([]));
    let logs = store.collection("action_server_logs");
    assert_eq!(logs.len(), 1);
    assert!(logs[0].get("type").is_none());
    assert_eq!(
        logs[0]["exception"],
        "Bot id and action name not found in slot"
    );
    assert_eq!(logs[0]["status"], "Failed");
    assert_eq!(logs[0]["request_id"], "bot-missing");
    assert_eq!(logs[0]["bot"], Value::Null);
}

#[actix_web::test]
async fn unknown_action_is_one_processor_log() {
    let (state, store) = memory();
    let app = test::init_service(create_app(state)).await;
    let (status, body, _) = call!(
        app,
        test::TestRequest::post().uri("/webhook").set_json(json!({
            "next_action": "missing_action",
            "tracker": tracker("bot-1", "s1")
        })),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["events"], json!([]));
    let logs = store.collection("action_server_logs");
    assert_eq!(logs.len(), 1);
    assert!(logs[0].get("type").is_none());
    assert_eq!(logs[0]["exception"], "No action found for given bot and name");
    assert_eq!(logs[0]["status"], "Failed");
}

#[actix_web::test]
async fn unported_type_is_swallowed() {
    let (state, store) = memory();
    store
        .insert_one(
            "actions",
            json!({"bot": "bot-1", "name": "file_ticket", "status": true, "type": "jira_action"}),
        )
        .await
        .unwrap();
    let app = test::init_service(create_app(state)).await;
    let (status, body, _) = call!(
        app,
        test::TestRequest::post().uri("/webhook").set_json(json!({
            "next_action": "file_ticket",
            "tracker": tracker("bot-1", "s1")
        })),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["events"], json!([]));
    let logs = store.collection("action_server_logs");
    assert_eq!(logs.len(), 1);
    assert!(logs[0].get("type").is_none());
    let exception = logs[0]["exception"].as_str().unwrap_or("");
    assert!(exception.contains("not available"));
}

#[actix_web::test]
async fn slot_set_survives_a_version_mismatch() {
    let (state, store) = memory();
    store
        .insert_one(
            "actions",
            json!({"bot": "bot-1", "name": "set_city", "status": true, "type": "slot_set_action"}),
        )
        .await
        .unwrap();
    store
        .insert_one(
            "slot_set_action",
            json!({
                "bot": "bot-1",
                "name": "set_city",
                "status": true,
                "set_slots": [
                    {"name": "city", "type": "from_value", "value": "Pune"},
                    {"name": "age", "type": "reset_slot"}
                ]
            }),
        )
        .await
        .unwrap();
    let app = test::init_service(create_app(state)).await;
    let (status, body, _) = call!(
        app,
        test::TestRequest::post().uri("/webhook").set_json(json!({
            "version": "1.0.0",
            "next_action": "set_city",
            "tracker": tracker("bot-1", "s1")
        })),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    let events = body["events"].as_array().unwrap();
    assert_eq!(events.len(), 2);
    assert_eq!(events[0]["event"], "slot");
    assert_eq!(events[0]["timestamp"], Value::Null);
    assert_eq!(events[0]["name"], "city");
    assert_eq!(events[0]["value"], "Pune");
    assert_eq!(events[1]["name"], "age");
    assert_eq!(events[1]["value"], Value::Null);
    assert_eq!(body["responses"], json!([]));
}

#[actix_web::test]
async fn voice_disconnect_utters_custom_json() {
    let (state, _) = memory();
    let app = test::init_service(create_app(state)).await;
    let (status, body, _) = call!(
        app,
        test::TestRequest::post().uri("/webhook").set_json(json!({
            "next_action": "kairon_voice_disconnect",
            "tracker": tracker("bot-1", "s1")
        })),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["events"], json!([]));
    assert_eq!(body["responses"][0]["custom"]["disconnect"], true);
}

#[actix_web::test]
async fn http_action_fills_slots_from_the_response() {
    let url = serve_ada();
    let (state, _) = memory();
    let store = state.store.clone();
    store
        .insert_one(
            "actions",
            json!({"bot": "bot-1", "name": "lookup_who", "status": true, "type": "http_action"}),
        )
        .await
        .unwrap();
    store
        .insert_one(
            "http_action_config",
            json!({
                "bot": "bot-1",
                "action_name": "lookup_who",
                "status": true,
                "http_url": url,
                "request_method": "GET",
                "content_type": "json",
                "headers": [],
                "params_list": [],
                "set_slots": [{
                    "name": "who_slot",
                    "value": "${data.who}",
                    "evaluation_type": "expression"
                }],
                "response": {
                    "dispatch": true,
                    "dispatch_type": "text",
                    "value": "Hello ${data.who}",
                    "evaluation_type": "expression"
                }
            }),
        )
        .await
        .unwrap();
    let app = test::init_service(create_app(state)).await;
    let (status, body, _) = call!(
        app,
        test::TestRequest::post().uri("/webhook").set_json(json!({
            "next_action": "lookup_who",
            "tracker": tracker("bot-1", "ada")
        })),
    )
    .await;
    assert_eq!(status, StatusCode::OK, "{body}");
    let events = body["events"].as_array().expect("events");
    let names: Vec<&str> = events
        .iter()
        .map(|event| event["name"].as_str().unwrap_or(""))
        .collect();
    assert_eq!(
        names,
        vec!["kairon_action_response", "http_status_code", "who_slot"]
    );
    assert_eq!(events[0]["value"], "Hello Ada");
    assert_eq!(events[1]["value"], 200);
    assert_eq!(events[2]["value"], "Ada");
    assert_eq!(body["responses"][0]["text"], "Hello Ada");
}

#[actix_web::test]
async fn callback_action_stores_a_decryptable_token() {
    let config = Config::for_tests();
    let key = config.fernet_key.clone();
    let base = config.callback_base_url.clone();
    let secret = fernet_encrypt("sekret", &key).expect("encrypt secret");
    let (state, store) = AppState::memory(config);
    store
        .insert_one(
            "actions",
            json!({"bot": "bot-1", "name": "make_link", "status": true, "type": "callback_action"}),
        )
        .await
        .unwrap();
    store
        .insert_one(
            "callback_config",
            json!({
                "bot": "bot-1",
                "name": "payments",
                "validation_secret": secret,
                "shorten_token": false,
                "standalone": false
            }),
        )
        .await
        .unwrap();
    store
        .insert_one(
            "callback_action_config",
            json!({
                "bot": "bot-1",
                "name": "make_link",
                "status": true,
                "callback_name": "payments",
                "bot_response": "Hello",
                "dynamic_url_slot_name": "callback_url",
                "dispatch_bot_response": true,
                "metadata_list": []
            }),
        )
        .await
        .unwrap();
    let app = test::init_service(create_app(state)).await;
    let (status, body, _) = call!(
        app,
        test::TestRequest::post().uri("/webhook").set_json(json!({
            "next_action": "make_link",
            "tracker": tracker("bot-1", "user-1")
        })),
    )
    .await;
    assert_eq!(status, StatusCode::OK, "{body}");
    let url = body["events"]
        .as_array()
        .and_then(|events| events.iter().find(|event| event["name"] == "callback_url"))
        .and_then(|event| event["value"].as_str())
        .unwrap_or("");
    assert!(url.contains("/d/"), "{url}");
    assert!(url.contains(&base), "{url}");
    assert_eq!(body["responses"][0]["text"], "Hello");
    let token = url.rsplit('/').next().unwrap_or("");
    let plain = fernet_decrypt(token, &key).expect("decrypt token");
    let info: Value = serde_json::from_str(&plain).expect("token json");
    assert_eq!(info["validation_secret"], "sekret");
    let saved = store.collection("callback_data");
    assert_eq!(saved.len(), 1);
    assert_eq!(saved[0]["callback_url"], url);
    assert_eq!(saved[0]["is_valid"], true);
}

#[actix_web::test]
async fn two_stage_fallback_offers_the_next_intent() {
    let (state, store) = memory();
    store
        .insert_one(
            "actions",
            json!({"bot": "bot-1", "name": "fallback", "status": true, "type": "two_stage_fallback"}),
        )
        .await
        .unwrap();
    store
        .insert_one(
            "kairon_two_stage_fallback_action",
            json!({
                "bot": "bot-1",
                "name": "fallback",
                "status": true,
                "fallback_message": "Did you mean",
                "text_recommendations": {"count": 1, "use_intent_ranking": true}
            }),
        )
        .await
        .unwrap();
    store
        .insert_one(
            "training_examples",
            json!({
                "bot": "bot-1",
                "intent": "greet",
                "text": "hello there",
                "status": true,
                "timestamp": 1
            }),
        )
        .await
        .unwrap();
    let app = test::init_service(create_app(state)).await;
    let (status, body, _) = call!(
        app,
        test::TestRequest::post().uri("/webhook").set_json(json!({
            "next_action": "fallback",
            "tracker": {
                "sender_id": "s1",
                "slots": {"bot": "bot-1"},
                "latest_message": {
                    "text": "huh",
                    "intent_ranking": [{"name": "nlu_fallback"}, {"name": "greet"}]
                }
            }
        })),
    )
    .await;
    assert_eq!(status, StatusCode::OK, "{body}");
    assert_eq!(body["responses"][0]["text"], "Did you mean");
    assert_eq!(body["responses"][0]["buttons"][0]["text"], "hello there");
    assert_eq!(body["responses"][0]["buttons"][0]["payload"], "hello there");
}

fn serve_ada() -> String {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
    let port = listener.local_addr().expect("addr").port();
    thread::spawn(move || {
        let Ok((mut stream, _)) = listener.accept() else {
            return;
        };
        let mut buf = Vec::new();
        let mut tmp = [0u8; 1024];
        loop {
            let Ok(n) = stream.read(&mut tmp) else {
                return;
            };
            if n == 0 {
                break;
            }
            buf.extend_from_slice(&tmp[..n]);
            if buf.windows(4).any(|window| window == b"\r\n\r\n") {
                break;
            }
        }
        let body = br#"{"who":"Ada"}"#;
        let header = format!(
            "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            body.len()
        );
        let _ = stream.write_all(header.as_bytes());
        let _ = stream.write_all(body);
    });
    format!("http://127.0.0.1:{port}/who/$SENDER_ID")
}
