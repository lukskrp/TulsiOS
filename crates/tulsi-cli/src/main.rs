//! `tulsi`, the TulsiOS command-line tool.
//!
//! Phase 1 offers read-only commands on a state file. Phase 2 adds
//! `install`, `remove`, `ext add`, `apply` and `rollback` via tulsid.

use std::path::Path;
use std::process::ExitCode;

use tulsi_state::State;

const DEFAULT_STATE: &str = "/etc/nixos/tulsi/state.json";

const USAGE: &str = "\
usage: tulsi <command> [FILE]

commands:
  validate [FILE]   check a state file against the TulsiOS schema
  show [FILE]       print a summary of a state file
  version           print the version

FILE defaults to /etc/nixos/tulsi/state.json";

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = args.get(1).map(String::as_str).unwrap_or(DEFAULT_STATE);

    match args.first().map(String::as_str) {
        Some("validate") => match State::load(Path::new(file)) {
            Ok(_) => {
                println!("{file}: valid");
                ExitCode::SUCCESS
            }
            Err(e) => fail(&format!("{file}: {e}")),
        },
        Some("show") => match State::load(Path::new(file)) {
            Ok(state) => {
                print_summary(&state);
                ExitCode::SUCCESS
            }
            Err(e) => fail(&format!("{file}: {e}")),
        },
        Some("version" | "--version") => {
            println!("tulsi {}", env!("CARGO_PKG_VERSION"));
            ExitCode::SUCCESS
        }
        Some("help" | "--help" | "-h") | None => {
            println!("{USAGE}");
            ExitCode::SUCCESS
        }
        Some(other) => fail(&format!("unknown command {other:?}\n\n{USAGE}")),
    }
}

fn print_summary(state: &State) {
    let list = |items: &[String]| {
        if items.is_empty() {
            "(none)".to_string()
        } else {
            items.join(", ")
        }
    };
    let services: Vec<String> = state
        .services
        .iter()
        .map(|(name, s)| format!("{name}={}", if s.enable { "on" } else { "off" }))
        .collect();

    println!("packages:            {}", list(&state.packages));
    println!("firefox extensions:  {}", list(&state.browser_extensions.firefox));
    println!("chromium extensions: {}", list(&state.browser_extensions.chromium));
    println!("services:            {}", list(&services));
}

fn fail(msg: &str) -> ExitCode {
    eprintln!("tulsi: {msg}");
    ExitCode::FAILURE
}
