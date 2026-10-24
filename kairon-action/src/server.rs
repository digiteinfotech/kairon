//! Actix Web action server: health routes, the webhook, and the security headers
//! the Python server adds around every response.

use std::sync::Arc;
use std::time::Instant;

use actix_web::body::MessageBody;
use actix_web::dev::{ServiceFactory, ServiceRequest, ServiceResponse};
use actix_web::http::header::{self, HeaderName, HeaderValue};
use actix_web::http::{Method, StatusCode};
use actix_web::middleware::{from_fn, Compress, Next};
use actix_web::web::{self, Data, PayloadConfig};
use actix_web::{App, Error, HttpRequest, HttpResponse, HttpServer};
use futures_util::StreamExt;
use serde_json::{json, Value};
use uuid::Uuid;

use crate::config::Config;
use crate::engine::process_actions;
use crate::error::ActionError;
use crate::store::{ActionStore, MemoryStore};

const MAX_BODY: usize = 32 * 1024 * 1024;
const REQUEST_ID: HeaderName = HeaderName::from_static("x-kairon-request-id");

const PERMISSIONS_POLICY: &str = "accelerometer=(), autoplay=(), camera=(), document-domain=(), encrypted-media=(), fullscreen=(), vibrate=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), picture-in-picture=(), sync-xhr=(), usb=()";
const HSTS: &str = "max-age=31536000; includeSubDomains; preload";
const CSP: &str = "default-src 'self'; frame-ancestors 'self'; form-action 'self'; base-uri 'self'; connect-src 'self'; frame-src 'self'; style-src 'self' https: 'unsafe-inline'; img-src 'self' https:; script-src 'self' https: 'unsafe-inline'";

#[derive(Clone)]
pub struct AppState {
    pub store: Arc<dyn ActionStore>,
    pub http: reqwest::Client,
    pub config: Arc<Config>,
}

impl AppState {
    pub fn memory(config: Config) -> (Self, Arc<MemoryStore>) {
        let store = Arc::new(MemoryStore::new());
        let state = Self::new(store.clone(), config);
        (state, store)
    }

    pub fn new(store: Arc<dyn ActionStore>, config: Config) -> Self {
        let http = http_client(&config);
        Self {
            store,
            http,
            config: Arc::new(config),
        }
    }
}

fn http_client(config: &Config) -> reqwest::Client {
    reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(config.request_timeout_secs))
        .build()
        .unwrap_or_else(|err| {
            tracing::error!("reqwest client with timeout failed: {err}");
            reqwest::Client::builder()
                .build()
                .expect("reqwest client")
        })
}

pub fn create_app(
    state: AppState,
) -> App<
    impl ServiceFactory<
        ServiceRequest,
        Response = ServiceResponse<impl MessageBody>,
        Error = Error,
        Config = (),
        InitError = (),
    >,
> {
    App::new()
        .app_data(Data::new(state))
        .app_data(PayloadConfig::new(MAX_BODY))
        .wrap(Compress::default())
        .wrap(from_fn(secure))
        .service(
            web::resource("/")
                .route(web::get().to(index))
                .route(web::route().method(Method::OPTIONS).to(preflight)),
        )
        .service(
            web::resource("/healthcheck")
                .route(web::get().to(health))
                .route(web::route().method(Method::OPTIONS).to(preflight)),
        )
        .service(
            web::resource("/webhook")
                .route(web::post().to(webhook))
                .route(web::route().method(Method::OPTIONS).to(preflight)),
        )
        .default_service(web::route().to(not_found))
}

pub async fn serve(state: AppState) -> std::io::Result<()> {
    let host = state.config.host.clone();
    let port = state.config.port;
    HttpServer::new(move || create_app(state.clone()))
        .bind((host.as_str(), port))?
        .run()
        .await
}

async fn index() -> HttpResponse {
    HttpResponse::Ok().json(json!({"message": "Kairon Action Server Up and Running"}))
}

async fn health() -> HttpResponse {
    HttpResponse::Ok().json(json!({"message": "health check ok"}))
}

async fn preflight() -> HttpResponse {
    HttpResponse::Ok()
        .insert_header((header::ACCESS_CONTROL_ALLOW_METHODS, "*"))
        .insert_header((header::ACCESS_CONTROL_ALLOW_HEADERS, "*"))
        .finish()
}

async fn not_found() -> HttpResponse {
    api_error(StatusCode::NOT_FOUND, 404, "Not Found")
}

async fn webhook(req: HttpRequest, mut payload: web::Payload, state: Data<AppState>) -> HttpResponse {
    let mut buf = Vec::new();
    while let Some(chunk) = payload.next().await {
        let chunk = match chunk {
            Ok(chunk) => chunk,
            Err(err) => {
                return api_error(StatusCode::UNPROCESSABLE_ENTITY, 422, err.to_string());
            }
        };
        if buf.len().saturating_add(chunk.len()) > MAX_BODY {
            return api_error(
                StatusCode::UNPROCESSABLE_ENTITY,
                422,
                "request body is too large",
            );
        }
        buf.extend_from_slice(&chunk);
    }
    let parsed = match serde_json::from_slice::<Value>(&buf) {
        Ok(value) => value,
        Err(err) => return api_error(StatusCode::UNPROCESSABLE_ENTITY, 422, err.to_string()),
    };
    if !parsed.is_object() {
        return api_error(
            StatusCode::UNPROCESSABLE_ENTITY,
            422,
            "request body must be a JSON object",
        );
    }
    let request_id = req
        .headers()
        .get(REQUEST_ID)
        .and_then(|value| value.to_str().ok())
        .unwrap_or("")
        .to_string();
    match process_actions(
        state.store.clone(),
        state.http.clone(),
        state.config.clone(),
        parsed,
        request_id,
    )
    .await
    {
        Ok(None) => HttpResponse::Ok().json(Value::Null),
        Ok(Some(body)) => HttpResponse::Ok().json(body),
        Err(ActionError::Rejected { message, action_name })
        | Err(ActionError::NotFound { message, action_name }) => HttpResponse::BadRequest().json(
            json!({"error": message, "action_name": action_name}),
        ),
        Err(ActionError::Failure(message)) => {
            tracing::error!("webhook failed: {message}");
            api_error(StatusCode::INTERNAL_SERVER_ERROR, 500, message)
        }
    }
}

fn api_error(status: StatusCode, code: u16, message: impl Into<String>) -> HttpResponse {
    HttpResponse::build(status).json(json!({
        "success": false,
        "error_code": code,
        "message": message.into(),
        "data": null
    }))
}

async fn secure<B>(
    req: ServiceRequest,
    next: Next<B>,
) -> Result<ServiceResponse<B>, Error>
where
    B: MessageBody + 'static,
{
    let request_id = incoming_request_id(req.headers());
    let path = req.path().to_string();
    let rid = authorization_param(req.headers());
    let origin = req
        .headers()
        .get(header::ORIGIN)
        .and_then(|value| value.to_str().ok())
        .map(str::to_string);
    let allowed = req
        .app_data::<Data<AppState>>()
        .map(|state| state.config.allowed_origins.clone())
        .unwrap_or_else(|| vec!["*".to_string()]);
    let req = write_request_id(req, &request_id);
    let started = Instant::now();
    let mut response = next.call(req).await?;
    let status = response.status().as_u16();
    let elapsed_ms = started.elapsed().as_secs_f64() * 1000.0;
    tracing::info!(
        "rid={rid} request path={path} completed_in={elapsed_ms:.2}ms status_code={status}"
    );
    let headers = response.headers_mut();
    insert_static(headers, REQUEST_ID, &request_id);
    insert_static(headers, header::STRICT_TRANSPORT_SECURITY, HSTS);
    insert_static(headers, header::REFERRER_POLICY, "no-referrer");
    insert_static(headers, header::CONTENT_SECURITY_POLICY, CSP);
    insert_static(headers, header::CACHE_CONTROL, "must-revalidate");
    insert_static(headers, header::X_CONTENT_TYPE_OPTIONS, "nosniff");
    insert_static(headers, header::SERVER, "Secure");
    insert_static(
        headers,
        HeaderName::from_static("permissions-policy"),
        PERMISSIONS_POLICY,
    );
    insert_static(
        headers,
        HeaderName::from_static("cross-origin-embedder-policy"),
        "require-corp",
    );
    insert_static(
        headers,
        HeaderName::from_static("cross-origin-opener-policy"),
        "same-origin",
    );
    insert_static(
        headers,
        HeaderName::from_static("cross-origin-resource-policy"),
        "same-origin",
    );
    let allow = match origin {
        Some(value) => value,
        None => allowed
            .first()
            .cloned()
            .unwrap_or_else(|| "*".to_string()),
    };
    insert_static(headers, header::ACCESS_CONTROL_ALLOW_ORIGIN, &allow);
    insert_static(headers, header::ACCESS_CONTROL_ALLOW_CREDENTIALS, "true");
    insert_static(
        headers,
        header::ACCESS_CONTROL_EXPOSE_HEADERS,
        "content-disposition",
    );
    Ok(response)
}

fn incoming_request_id(headers: &header::HeaderMap) -> String {
    headers
        .get(REQUEST_ID)
        .and_then(|value| value.to_str().ok())
        .map(str::trim)
        .filter(|text| !text.is_empty())
        .map(str::to_string)
        .unwrap_or_else(|| Uuid::new_v4().to_string())
}

fn authorization_param(headers: &header::HeaderMap) -> String {
    let Some(raw) = headers
        .get(header::AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
    else {
        return String::new();
    };
    raw.split_once(' ')
        .map(|(_, param)| param.to_string())
        .unwrap_or_default()
}

fn write_request_id(mut req: ServiceRequest, id: &str) -> ServiceRequest {
    if let Ok(value) = HeaderValue::from_str(id) {
        req.headers_mut().insert(REQUEST_ID, value);
    }
    req
}

fn insert_static(headers: &mut header::HeaderMap, name: HeaderName, value: &str) {
    if let Ok(value) = HeaderValue::from_str(value) {
        headers.insert(name, value);
    }
}
