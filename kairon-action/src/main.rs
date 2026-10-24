use std::process::ExitCode;
use std::sync::Arc;

use kairon_action::{serve, AppState, Config, MongoActionStore};

#[actix_web::main]
async fn main() -> ExitCode {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    let config = Config::load();
    let store = match MongoActionStore::connect(&config).await {
        Ok(store) => store,
        Err(err) => {
            eprintln!("mongo connect failed: {err}");
            return ExitCode::from(1);
        }
    };
    if let Err(err) = store.ping().await {
        eprintln!("mongo ping failed: {err}");
        return ExitCode::from(1);
    }
    let host = config.host.clone();
    let port = config.port;
    let state = AppState::new(Arc::new(store), config);
    tracing::info!("kairon action server listening on {host}:{port}");
    if let Err(err) = serve(state).await {
        eprintln!("server failed: {err}");
        return ExitCode::from(1);
    }
    ExitCode::SUCCESS
}
