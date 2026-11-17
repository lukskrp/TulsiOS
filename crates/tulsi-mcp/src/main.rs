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
mod packaging;
mod backend;
mod server;
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
