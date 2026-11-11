//! Human approval for every change an agent asks for.
//!
//! Channels, in order (mode `auto`):
//! 1. A desktop dialog (`ocimum-approve`, from the Software Center package),
//!    when a graphical session is reachable. It is shown by the OS, outside
//!    the agent's control, and defaults to Reject.
//! 2. MCP elicitation through the agent's client, if the client supports it.
//! 3. Otherwise the change is refused. There is no silent approval.

use std::process::Stdio;
use std::time::Duration;

use serde::Serialize;
use serde_json::{json, Value};
use tokio::io::{AsyncRead, AsyncWrite, AsyncWriteExt};
use tokio::process::Command;

use crate::transport::Transport;

const DIALOG_TIMEOUT: Duration = Duration::from_secs(10 * 60);
const MAX_ELICIT_DIFF: usize = 4000;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    Auto,
    Dialog,
    Elicitation,
}

impl std::str::FromStr for Mode {
    type Err = String;
    fn from_str(s: &str) -> Result<Self, String> {
        match s {
            "auto" => Ok(Mode::Auto),
            "dialog" => Ok(Mode::Dialog),
            "elicitation" => Ok(Mode::Elicitation),
            other => Err(format!(
                "unknown approval mode {other:?} (auto, dialog, elicitation)"
            )),
        }
    }
}

/// What the human is asked to approve. Also the JSON the dialog reads on stdin.
#[derive(Debug, Clone, Serialize)]
pub struct Request {
    pub title: String,
    /// The agent's stated reason, shown verbatim.
    pub reason: String,
    pub changes: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub diff: Option<String>,
    pub requester: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Decision {
    /// Approved, through the named channel.
    Approved(&'static str),
    Rejected(String),
}

pub struct Approver {
    pub mode: Mode,
    /// Dialog program and arguments; reads a `Request` as JSON on stdin,
    /// exits 0 to approve and 1 to reject.
    pub command: Vec<String>,
}

impl Approver {
    pub async fn ask<R, W>(
        &self,
        req: &Request,
        transport: &mut Transport<R, W>,
        client_elicits: bool,
    ) -> Decision
    where
        R: AsyncRead + Unpin,
        W: AsyncWrite + Unpin,
    {
        match self.mode {
            Mode::Dialog => self.dialog(req).await,
            Mode::Elicitation if client_elicits => elicit(req, transport).await,
            Mode::Elicitation => Decision::Rejected(
                "approval mode is 'elicitation' but this MCP client does not support elicitation"
                    .into(),
            ),
            Mode::Auto if self.dialog_available() => self.dialog(req).await,
            Mode::Auto if client_elicits => elicit(req, transport).await,
            Mode::Auto => Decision::Rejected(
                "no way to ask the user for approval: no graphical session is reachable and this \
                 MCP client does not support elicitation"
                    .into(),
            ),
        }
    }

    fn dialog_available(&self) -> bool {
        let graphical =
            std::env::var_os("DISPLAY").is_some() || std::env::var_os("WAYLAND_DISPLAY").is_some();
        graphical && self.command.first().is_some_and(|p| program_exists(p))
    }

    async fn dialog(&self, req: &Request) -> Decision {
        let Some((program, args)) = self.command.split_first() else {
            return Decision::Rejected("no approval dialog is configured".into());
        };
        let child = Command::new(program)
            .args(args)
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .kill_on_drop(true)
            .spawn();
        let mut child = match child {
            Ok(c) => c,
            Err(e) => {
                return Decision::Rejected(format!("cannot start approval dialog {program}: {e}"))
            }
        };
        if let Some(mut stdin) = child.stdin.take() {
            let payload = serde_json::to_vec(req).expect("request serializes");
            let _ = stdin.write_all(&payload).await;
        }
        match tokio::time::timeout(DIALOG_TIMEOUT, child.wait()).await {
            Err(_) => Decision::Rejected("the approval dialog timed out without an answer".into()),
            Ok(Err(e)) => Decision::Rejected(format!("approval dialog failed: {e}")),
            Ok(Ok(status)) => match status.code() {
                Some(0) => Decision::Approved("desktop dialog"),
                Some(1) => Decision::Rejected("the user rejected the change".into()),
                _ => Decision::Rejected(format!("approval dialog failed ({status})")),
            },
        }
    }
}

fn program_exists(program: &str) -> bool {
    if program.contains('/') {
        return std::path::Path::new(program).is_file();
    }
    std::env::var_os("PATH")
        .map(|paths| std::env::split_paths(&paths).any(|dir| dir.join(program).is_file()))
        .unwrap_or(false)
}

async fn elicit<R, W>(req: &Request, transport: &mut Transport<R, W>) -> Decision
where
    R: AsyncRead + Unpin,
    W: AsyncWrite + Unpin,
{
    let mut message = format!(
        "{}\n\nRequested by: {}\nReason given: {}\n\nChanges:\n",
        req.title, req.requester, req.reason
    );
    for change in &req.changes {
        message.push_str(&format!("  • {change}\n"));
    }
    if let Some(diff) = &req.diff {
        let shown: String = diff.chars().take(MAX_ELICIT_DIFF).collect();
        message.push_str(&format!("\n{shown}"));
        if diff.chars().count() > MAX_ELICIT_DIFF {
            message.push_str("\n… (diff truncated)");
        }
    }
    let params = json!({
        "message": message,
        "requestedSchema": {
            "type": "object",
            "properties": {
                "approve": {
                    "type": "boolean",
                    "title": "Approve this system change",
                    "description": "The system configuration is rebuilt. It can be undone later."
                }
            },
            "required": ["approve"]
        }
    });
    match transport.request("elicitation/create", params).await {
        Ok(result) if accepted(&result) => Decision::Approved("client elicitation"),
        Ok(_) => Decision::Rejected("the user declined the change".into()),
        Err(e) => Decision::Rejected(format!("could not ask the user: {e}")),
    }
}

fn accepted(result: &Value) -> bool {
    result["action"] == "accept" && result["content"]["approve"] == true
}
