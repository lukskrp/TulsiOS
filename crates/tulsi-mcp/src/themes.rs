//! Theme tools (ADR 0021): list the palettes, switch the person's desktop to one,
//! and undo that. A theme is the person's own setting, changed in their session
//! and undone with `undo_theme`, so it needs no approval (the reversibility rule):
//! nothing outside their home changes. It works only when this server runs as the
//! person, in their session (a coding agent they started). An agent with its own
//! identity (Starah's `starah run`) has no session to theme, and is told so.

use std::path::Path;
use std::time::Duration;

use serde_json::{json, Value};
use tokio::process::Command;

const TIMEOUT: Duration = Duration::from_secs(120);

fn program() -> String {
    std::env::var("TULSI_THEME").unwrap_or_else(|_| "tulsi-theme".into())
}

/// The person's desktop session is reachable: a session bus and a display.
fn in_session() -> bool {
    let bus = std::env::var_os("DBUS_SESSION_BUS_ADDRESS").is_some()
        || std::env::var_os("XDG_RUNTIME_DIR").is_some_and(|d| Path::new(&d).join("bus").exists());
    bus && std::env::var_os("DISPLAY").is_some()
}

const NO_SESSION: &str = "Themes are each person's own setting, and this agent is not running in their \
desktop session, so it can't change theirs. Suggest the Themes app, or `tulsi-theme set <theme>` in their terminal.";

async fn run(args: &[&str]) -> Result<String, String> {
    let out = tokio::time::timeout(TIMEOUT, Command::new(program()).args(args).output())
        .await
        .map_err(|_| "tulsi-theme took too long".to_string())?
        .map_err(|e| format!("cannot run tulsi-theme: {e}"))?;
    let stdout = String::from_utf8_lossy(&out.stdout).trim().to_string();
    if out.status.success() {
        Ok(stdout)
    } else {
        let stderr = String::from_utf8_lossy(&out.stderr).trim().to_string();
        Err(if stderr.is_empty() { stdout } else { stderr })
    }
}

/// `list_themes`: the palettes, which is on, dark or light.
pub async fn list() -> Result<(String, Value), String> {
    let text = run(&["list", "--json"]).await?;
    let themes: Value = serde_json::from_str(&text).map_err(|e| format!("tulsi-theme list: {e}"))?;
    let lines = themes
        .as_array()
        .into_iter()
        .flatten()
        .map(|t| {
            format!(
                "{}{} ({}, {})",
                if t["current"].as_bool() == Some(true) { "* " } else { "  " },
                t["slug"].as_str().unwrap_or("?"),
                t["name"].as_str().unwrap_or("?"),
                t["mode"].as_str().unwrap_or("?"),
            )
        })
        .collect::<Vec<_>>()
        .join("\n");
    Ok((lines, json!({ "themes": themes })))
}

/// `set_theme`: switch the person's desktop to a palette.
pub async fn set(args: &Value) -> Result<(String, Value), String> {
    let theme = args["theme"]
        .as_str()
        .filter(|t| !t.is_empty() && !t.starts_with('-'))
        .ok_or("missing required argument \"theme\"")?;
    if !in_session() {
        return Err(NO_SESSION.into());
    }
    let background = args["background"].as_u64().unwrap_or(0).to_string();
    let said = run(&["set", theme, "--background", &background]).await?;
    Ok((
        format!("{said}\nUndo with undo_theme."),
        json!({ "receipt": { "theme": theme, "background": background } }),
    ))
}

/// `undo_theme`: back to the theme before (or the desktop's own look).
pub async fn undo() -> Result<(String, Value), String> {
    if !in_session() {
        return Err(NO_SESSION.into());
    }
    let said = run(&["undo"]).await?;
    Ok((said.clone(), json!({ "receipt": { "undone": true, "now": said } })))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    /// One test, since it sets process-wide environment variables.
    #[tokio::test]
    async fn theme_tools() {
        let dir = std::env::temp_dir().join(format!("tulsi-mcp-themes-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let fake = dir.join("tulsi-theme");
        std::fs::write(
            &fake,
            "#!/bin/sh\ncase \"$1\" in\n\
             list) echo '[{\"slug\":\"nord\",\"name\":\"Nord\",\"mode\":\"dark\",\"current\":true}]';;\n\
             set) echo \"$2 is on\";;\n\
             undo) echo 'back to Nord';;\n\
             esac\n",
        )
        .unwrap();
        std::fs::set_permissions(&fake, std::fs::Permissions::from_mode(0o755)).unwrap();
        unsafe {
            std::env::set_var("TULSI_THEME", &fake);
            std::env::remove_var("DISPLAY");
            std::env::remove_var("DBUS_SESSION_BUS_ADDRESS");
            std::env::remove_var("XDG_RUNTIME_DIR");
        }

        let (text, data) = list().await.unwrap();
        assert!(text.contains("* nord (Nord, dark)"), "{text}");
        assert_eq!(data["themes"][0]["slug"], "nord");

        // No session: refused, with what to suggest instead.
        let err = set(&json!({ "theme": "nord" })).await.unwrap_err();
        assert!(err.contains("Themes app"), "{err}");
        assert!(set(&json!({ "theme": "--evil" })).await.is_err());

        unsafe {
            std::env::set_var("DISPLAY", ":0");
            std::env::set_var("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/1000/bus");
        }
        let (text, data) = set(&json!({ "theme": "kanagawa" })).await.unwrap();
        assert!(text.starts_with("kanagawa is on"), "{text}");
        assert_eq!(data["receipt"]["theme"], "kanagawa");
        let (text, _) = undo().await.unwrap();
        assert_eq!(text, "back to Nord");
        std::fs::remove_dir_all(&dir).ok();
    }
}
