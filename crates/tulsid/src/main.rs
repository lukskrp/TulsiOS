//! tulsid, the TulsiOS system daemon.
//!
//! Owns `<flakeDir>/tulsi/state.json`, serves `org.tulsi.Manager1` on the
//! system bus, authorizes changes through polkit, rebuilds the system and
//! records every successful change as a git commit in `<flakeDir>`.
//!
//! usage: tulsid [--config FILE] [--session]

mod config;
mod git;
mod polkit;
mod service;

use std::path::PathBuf;
use std::process::ExitCode;

use tulsi_client::{BUS_NAME, OBJECT_PATH};

const DEFAULT_CONFIG: &str = "/etc/tulsi/tulsid.json";

#[tokio::main]
async fn main() -> ExitCode {
    match run().await {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("tulsid: {e}");
            ExitCode::FAILURE
        }
    }
}

async fn run() -> Result<(), String> {
    let mut config_path = PathBuf::from(DEFAULT_CONFIG);
    let mut session = false;
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--config" => config_path = args.next().ok_or("--config needs a value")?.into(),
            "--session" => session = true,
            "--version" => {
                println!("tulsid {}", env!("CARGO_PKG_VERSION"));
                return Ok(());
            }
            other => return Err(format!("unknown argument {other:?}")),
        }
    }

    let cfg = config::Config::load(&config_path)?;
    git::init_repo(&cfg).await?;

    let manager = service::Manager::new(cfg);
    let builder = if session {
        zbus::connection::Builder::session()
    } else {
        zbus::connection::Builder::system()
    }
    .map_err(|e| format!("D-Bus: {e}"))?;

    let _conn = builder
        .name(BUS_NAME)
        .and_then(|b| b.serve_at(OBJECT_PATH, manager))
        .map_err(|e| format!("D-Bus: {e}"))?
        .build()
        .await
        .map_err(|e| format!("D-Bus: {e}"))?;

    eprintln!("tulsid {} ready on {BUS_NAME}", env!("CARGO_PKG_VERSION"));
    std::future::pending::<()>().await;
    Ok(())
}
