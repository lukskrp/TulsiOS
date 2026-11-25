//! Drivers tool (ADR 0029): what hardware this computer has and the driver
//! choices for it, from `tulsi-drivers list --json`. Read only: a driver change
//! takes effect at the next restart and only the person can keep it, so agents
//! change drivers with `tulsi-drivers set` after asking the person.

use std::time::Duration;

use serde_json::Value;
use tokio::process::Command;

const TIMEOUT: Duration = Duration::from_secs(60);

fn program() -> String {
    std::env::var("TULSI_DRIVERS").unwrap_or_else(|_| "tulsi-drivers".into())
}

/// `list_drivers`: one line per device and choice; the JSON as data.
pub async fn list() -> Result<(String, Value), String> {
    let out = tokio::time::timeout(
        TIMEOUT,
        Command::new(program()).args(["list", "--json"]).output(),
    )
    .await
    .map_err(|_| "tulsi-drivers took too long".to_string())?
    .map_err(|e| format!("cannot run tulsi-drivers: {e}"))?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).trim().to_string());
    }
    let data: Value =
        serde_json::from_slice(&out.stdout).map_err(|e| format!("tulsi-drivers list: {e}"))?;
    let mut lines = Vec::new();
    for row in data["rows"].as_array().into_iter().flatten() {
        lines.push(format!(
            "{} ({}): {}",
            row["title"].as_str().unwrap_or("?"),
            row["subtitle"].as_str().unwrap_or(""),
            row["status"].as_str().unwrap_or("")
        ));
        for c in row["choices"].as_array().into_iter().flatten() {
            let mut tags = Vec::new();
            if c["selected"].as_bool() == Some(true) {
                tags.push("chosen".to_string());
            }
            if c["recommended"].as_bool() == Some(true) {
                tags.push("recommended".to_string());
            }
            if c["unfree"].as_bool() == Some(true) {
                tags.push("unfree".to_string());
            }
            if c["available"].as_bool() == Some(false) {
                tags.push(format!(
                    "not available: {}",
                    c["reason"].as_str().unwrap_or("")
                ));
            }
            lines.push(format!(
                "  choice {}: {}{}",
                c["id"].as_str().unwrap_or("?"),
                c["label"].as_str().unwrap_or("?"),
                if tags.is_empty() {
                    String::new()
                } else {
                    format!(" [{}]", tags.join(", "))
                }
            ));
        }
        for e in row["extras"].as_array().into_iter().flatten() {
            lines.push(format!(
                "  extra {}: {} [{}]",
                e["id"].as_str().unwrap_or("?"),
                e["label"].as_str().unwrap_or("?"),
                if e["on"].as_bool() == Some(true) {
                    "on"
                } else {
                    "off"
                }
            ));
        }
    }
    Ok((lines.join("\n"), data))
}
