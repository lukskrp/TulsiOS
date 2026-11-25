//! tulsi-mcp: Model Context Protocol server for TulsiOS (stdio transport).
//!
//! Lets AI agents search packages, inspect the system and propose changes.
//! Every change is shown to the human for approval before tulsid applies it.
//!
//! usage: tulsi-mcp [--approval auto|dialog|elicitation|starah] [--approver PROGRAM [ARGS…]]
//!
//! With `--approver`, that program is always asked (mode `dialog`) unless
//! `--approval` says otherwise. It must come last: it takes the remaining args.
//!
//! Register with an MCP client, e.g. Claude Code:
//!     claude mcp add tulsi -- tulsi-mcp

mod approval;
mod backend;
mod packaging;
mod server;
mod themes;
mod transport;

use std::process::ExitCode;

use approval::{Approver, Mode};

const DEFAULT_APPROVER: &str = "ocimum-approve";

#[tokio::main]
async fn main() -> ExitCode {
    let mut mode = std::env::var("TULSI_MCP_APPROVAL")
        .ok()
        .map(|m| m.parse::<Mode>())
        .transpose();
    let mut command: Vec<String> = vec![DEFAULT_APPROVER.into()];
    let mut approver_given = false;

    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--approval" => mode = args.next().map(|m| m.parse()).transpose(),
            "--approver" => {
                command = args.by_ref().collect();
                approver_given = true;
                if command.is_empty() {
                    eprintln!("tulsi-mcp: --approver needs a program");
                    return ExitCode::FAILURE;
                }
            }
            "--version" => {
                println!("tulsi-mcp {}", env!("CARGO_PKG_VERSION"));
                return ExitCode::SUCCESS;
            }
            other => {
                eprintln!("tulsi-mcp: unknown argument {other:?}");
                return ExitCode::FAILURE;
            }
        }
    }
    let mode = match mode {
        // An explicitly named approver is always used, display or not.
        Ok(m) => m.unwrap_or(if approver_given {
            Mode::Dialog
        } else {
            Mode::Auto
        }),
        Err(e) => {
            eprintln!("tulsi-mcp: {e}");
            return ExitCode::FAILURE;
        }
    };

    // Started by a coding agent the person runs (claude mcp add tulsi -- tulsi-mcp):
    // serve as that agent's own Starah account, so the person's level for it decides
    // (ADR 0026). Only in the default mode; an explicit mode is the person's choice.
    if mode == Mode::Auto && !approver_given {
        if let Some(err) = run_as_starah_agent() {
            eprintln!("tulsi-mcp: {err}");
            return ExitCode::FAILURE;
        }
    }

    let backend = match backend::Dbus::connect().await {
        Ok(b) => b,
        Err(e) => {
            eprintln!("tulsi-mcp: {e}");
            return ExitCode::FAILURE;
        }
    };
    let mut transport = transport::Transport::new(tokio::io::stdin(), tokio::io::stdout());
    server::Server::new(backend, Approver { mode, command })
        .serve(&mut transport)
        .await;
    ExitCode::SUCCESS
}

/// Replaces this process with `starah run --agent NAME -- tulsi-mcp --approval
/// starah` when a known agent CLI started it and Starah declares an agent for it.
/// Returns only on failure (or with None when there is nothing to do).
fn run_as_starah_agent() -> Option<String> {
    use std::os::unix::process::CommandExt;
    use tulsi_client::agents;

    let name = agents::detect_here()?;
    let agent = agents::starah_agent(&name, &agents::declared_agents())?;
    let me = ["/run/current-system/sw/bin/tulsi-mcp"]
        .into_iter()
        .map(std::path::PathBuf::from)
        .find(|p| p.exists())
        .or_else(|| std::env::current_exe().ok())?;
    eprintln!("tulsi-mcp: started by {name}; serving as Starah agent {agent:?}");
    let err = std::process::Command::new("starah")
        .args(["run", "--agent", &agent, "--"])
        .arg(me)
        .args(["--approval", "starah"])
        .exec();
    Some(format!("cannot start through Starah: {err}"))
}
