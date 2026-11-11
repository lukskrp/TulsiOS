//! `tulsi`, the TulsiOS command-line tool.
//!
//! Talks to tulsid over D-Bus for everything that changes the system, so
//! no Nix knowledge (and no sudo) is needed: polkit asks for confirmation.

use std::io::IsTerminal;
use std::path::Path;
use std::process::ExitCode;

use futures_util::StreamExt;
use tulsi_client::{HistoryEntry, ManagerProxy, PackageInfo, Plan};
use tulsi_state::{Browser, Op, State};

/// `println!` that exits quietly when stdout is closed early
/// (e.g. `tulsi history | head -1`) instead of panicking.
macro_rules! out {
    ($($arg:tt)*) => {{
        use std::io::Write as _;
        if let Err(e) = writeln!(std::io::stdout().lock(), $($arg)*) {
            if e.kind() == std::io::ErrorKind::BrokenPipe {
                std::process::exit(0);
            }
        }
    }};
}

const USAGE: &str = "\
usage: tulsi [-n|--dry-run] [-q|--quiet] <command>

change the system (asks for authorization):
  install PKG...                    install nixpkgs packages (e.g. vlc, python3Packages.requests)
  remove PKG...                     remove packages installed with tulsi
  ext add|remove BROWSER ID         browser extension (firefox | chromium) by store id
  service enable|disable NAME       toggle a NixOS service (services.NAME.enable)
  undo                              revert the most recent change (alias: rollback)

inspect:
  search WORDS...                   find packages (installed ones are marked *)
  status                            show the managed state
  history [N]                       show the last N changes (default 10)
  validate FILE                     check a state file
  show FILE                         summarize a state file
  version

options:
  -n, --dry-run   show what would change, do nothing
  -q, --quiet     do not print rebuild output";

struct Options {
    dry_run: bool,
    quiet: bool,
}

#[tokio::main]
async fn main() -> ExitCode {
    let mut opts = Options {
        dry_run: false,
        quiet: false,
    };
    let mut args = Vec::new();
    for arg in std::env::args().skip(1) {
        match arg.as_str() {
            "-n" | "--dry-run" => opts.dry_run = true,
            "-q" | "--quiet" => opts.quiet = true,
            _ => args.push(arg),
        }
    }
    let args: Vec<&str> = args.iter().map(String::as_str).collect();

    match run(&opts, &args).await {
        Ok(code) => code,
        Err(msg) => {
            eprintln!("tulsi: {msg}");
            ExitCode::FAILURE
        }
    }
}

async fn run(opts: &Options, args: &[&str]) -> Result<ExitCode, String> {
    let ops = match args {
        ["install", pkgs @ ..] if !pkgs.is_empty() => pkgs
            .iter()
            .map(|p| Op::AddPackage {
                name: p.to_string(),
            })
            .collect(),
        ["remove" | "uninstall", pkgs @ ..] if !pkgs.is_empty() => pkgs
            .iter()
            .map(|p| Op::RemovePackage {
                name: p.to_string(),
            })
            .collect(),
        ["ext", action @ ("add" | "remove"), browser, id] => {
            let browser: Browser = browser.parse()?;
            let id = id.to_string();
            if *action == "add" {
                vec![Op::AddExtension { browser, id }]
            } else {
                vec![Op::RemoveExtension { browser, id }]
            }
        }
        ["service", action @ ("enable" | "disable"), name] => {
            vec![Op::SetService {
                name: name.to_string(),
                enable: *action == "enable",
            }]
        }
        ["undo" | "rollback"] => return undo(opts).await,
        ["search", words @ ..] if !words.is_empty() => return search(&words.join(" ")).await,
        ["status"] => {
            let state = State::from_json(&proxy().await?.get_state().await.map_err(dbus)?)
                .map_err(|e| e.to_string())?;
            print_summary(&state);
            return Ok(ExitCode::SUCCESS);
        }
        ["history", rest @ ..] if rest.len() <= 1 => {
            let n = match rest.first() {
                Some(n) => n.parse().map_err(|_| format!("not a number: {n}"))?,
                None => 10,
            };
            return history(n).await;
        }
        ["validate", file] => {
            State::load(Path::new(file)).map_err(|e| format!("{file}: {e}"))?;
            out!("{file}: valid");
            return Ok(ExitCode::SUCCESS);
        }
        ["show", file] => {
            print_summary(&State::load(Path::new(file)).map_err(|e| format!("{file}: {e}"))?);
            return Ok(ExitCode::SUCCESS);
        }
        ["version" | "--version"] => {
            out!("tulsi {}", env!("CARGO_PKG_VERSION"));
            return Ok(ExitCode::SUCCESS);
        }
        [] | ["help" | "--help" | "-h"] => {
            out!("{USAGE}");
            return Ok(ExitCode::SUCCESS);
        }
        _ => return Err(format!("invalid arguments: {}\n\n{USAGE}", args.join(" "))),
    };
    change(opts, ops).await
}

async fn proxy() -> Result<ManagerProxy<'static>, String> {
    let conn = tulsi_client::connect()
        .await
        .map_err(|e| format!("cannot connect to D-Bus: {e}"))?;
    ManagerProxy::new(&conn).await.map_err(dbus)
}

fn dbus(e: zbus::Error) -> String {
    match e {
        zbus::Error::MethodError(name, Some(msg), _) => {
            let kind = name.as_str().trim_start_matches("org.tulsi.Error.");
            if name.as_str() == "org.freedesktop.DBus.Error.ServiceUnknown" {
                "tulsid is not running (is tulsi.daemon.enable set?)".into()
            } else {
                format!("{kind}: {msg}")
            }
        }
        other => other.to_string(),
    }
}

async fn change(opts: &Options, ops: Vec<Op>) -> Result<ExitCode, String> {
    let proxy = proxy().await?;
    let ops_json = serde_json::to_string(&ops).expect("ops serialize");

    let plan: Plan = serde_json::from_str(&proxy.plan(&ops_json).await.map_err(dbus)?)
        .map_err(|e| format!("bad reply from tulsid: {e}"))?;
    if plan.changes.is_empty() {
        out!("Nothing to change.");
        return Ok(ExitCode::SUCCESS);
    }
    for line in &plan.changes {
        out!("{line}");
    }
    if opts.dry_run {
        return Ok(ExitCode::SUCCESS);
    }

    let proxy_ref = &proxy;
    run_job(opts, proxy_ref, || async move {
        proxy_ref.apply(&ops_json).await
    })
    .await
}

async fn undo(opts: &Options) -> Result<ExitCode, String> {
    if opts.dry_run {
        return Err("--dry-run is not supported for undo; see `tulsi history`".into());
    }
    let proxy = proxy().await?;
    let proxy_ref = &proxy;
    run_job(opts, proxy_ref, || async move { proxy_ref.undo().await }).await
}

/// Subscribes to job signals, starts the job and follows it to the end.
async fn run_job<F, Fut>(
    opts: &Options,
    proxy: &ManagerProxy<'_>,
    start: F,
) -> Result<ExitCode, String>
where
    F: FnOnce() -> Fut,
    Fut: std::future::Future<Output = zbus::Result<u64>>,
{
    // Subscribe first so no signal is missed.
    let mut progress = proxy.receive_progress().await.map_err(dbus)?;
    let mut finished = proxy.receive_finished().await.map_err(dbus)?;

    let agent = spawn_tty_auth_agent();
    let started = start().await;
    drop(agent);
    let job = started.map_err(dbus)?;
    if job == 0 {
        out!("Nothing to change.");
        return Ok(ExitCode::SUCCESS);
    }
    out!("Applying (job {job})…");

    loop {
        tokio::select! {
            Some(sig) = progress.next() => {
                if let Ok(args) = sig.args() {
                    if args.job == job && !opts.quiet {
                        out!("  │ {}", args.line);
                    }
                }
            }
            Some(sig) = finished.next() => {
                if let Ok(args) = sig.args() {
                    if args.job == job {
                        return if args.success {
                            out!("Done: {}", args.message);
                            Ok(ExitCode::SUCCESS)
                        } else {
                            Err(args.message.clone())
                        };
                    }
                }
            }
            else => return Err("lost connection to tulsid".into()),
        }
    }
}

/// When run from a terminal with no graphical polkit agent, start
/// `pkttyagent` so polkit can ask for the password here.
struct TtyAgent(std::process::Child);

impl Drop for TtyAgent {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn spawn_tty_auth_agent() -> Option<TtyAgent> {
    let has_tty = std::fs::OpenOptions::new()
        .read(true)
        .write(true)
        .open("/dev/tty")
        .is_ok();
    if !has_tty
        || !std::io::stdin().is_terminal()
        || std::env::var(tulsi_client::BUS_ENV).as_deref() == Ok("session")
    {
        return None;
    }
    let child = std::process::Command::new("pkttyagent")
        .args(["--process", &std::process::id().to_string(), "--fallback"])
        .spawn()
        .ok()?;
    // Give the agent a moment to register before polkit is consulted.
    std::thread::sleep(std::time::Duration::from_millis(300));
    Some(TtyAgent(child))
}

async fn search(query: &str) -> Result<ExitCode, String> {
    let results: Vec<PackageInfo> =
        serde_json::from_str(&proxy().await?.search(query, 25).await.map_err(dbus)?)
            .map_err(|e| format!("bad reply from tulsid: {e}"))?;
    if results.is_empty() {
        out!("No packages match \"{query}\".");
    }
    for p in results {
        let mark = if p.installed { '*' } else { ' ' };
        let unfree = if p.unfree { " [unfree]" } else { "" };
        out!(
            "{mark} {:<32} {:<14} {}{unfree}",
            p.attr,
            p.version,
            p.description
        );
    }
    Ok(ExitCode::SUCCESS)
}

async fn history(n: u32) -> Result<ExitCode, String> {
    let entries: Vec<HistoryEntry> =
        serde_json::from_str(&proxy().await?.history(n).await.map_err(dbus)?)
            .map_err(|e| format!("bad reply from tulsid: {e}"))?;
    for e in entries {
        out!("{}  {}  {}", e.commit, format_time(e.time), e.summary);
    }
    Ok(ExitCode::SUCCESS)
}

fn format_time(unix: i64) -> String {
    // UTC, without pulling in a date crate.
    let days = unix.div_euclid(86_400);
    let secs = unix.rem_euclid(86_400);
    let (y, m, d) = civil_from_days(days);
    format!(
        "{y:04}-{m:02}-{d:02} {:02}:{:02}",
        secs / 3600,
        secs % 3600 / 60
    )
}

/// Howard Hinnant's days-to-civil algorithm.
fn civil_from_days(z: i64) -> (i64, u32, u32) {
    let z = z + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let m = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    (yoe + era * 400 + i64::from(m <= 2), m, d)
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

    out!("packages:            {}", list(&state.packages));
    out!(
        "firefox extensions:  {}",
        list(&state.browser_extensions.firefox)
    );
    out!(
        "chromium extensions: {}",
        list(&state.browser_extensions.chromium)
    );
    out!("services:            {}", list(&services));
}

#[cfg(test)]
mod tests {
    #[test]
    fn formats_time() {
        assert_eq!(super::format_time(0), "1970-01-01 00:00");
        assert_eq!(super::format_time(1_794_484_800), "2026-11-12 12:00");
    }
}
