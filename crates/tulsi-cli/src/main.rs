//! `tulsi`, the TulsiOS command-line tool.
//!
//! Talks to tulsid over D-Bus for everything that changes the system, so
//! no Nix knowledge (and no sudo) is needed: polkit asks for confirmation.

use std::io::IsTerminal;
use std::path::Path;
use std::process::ExitCode;

use futures_util::StreamExt;
use tulsi_client::{
    Candidate, HistoryEntry, ManagerProxy, MatchHint, PackageInfo, Plan, UndoPlan, UpgradeInfo,
};
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
  keep-source NAME on|off           keep the download a package made on this computer is
                                    built from (on), or let cleanup remove it (off)
  undo [CHANGE]                     revert the most recent change, or the change with
                                    that id from `tulsi history` (alias: rollback)
  upgrade                           move to the newest TulsiOS release (undo goes back)
  upgrade --check [--notify]        is a newer release out? (--notify: as a desktop
                                    notification with an Upgrade button)

inspect:
  search WORDS...                   find packages (installed ones are marked *)
  match [--tool TOOL] NAME...       what TulsiOS installs for another system's package
                                    name (e.g. `match --tool apt python3-requests`)
  inspect FILE                      what a downloaded file is, as JSON (kind, name,
                                    version, programs inside)

package downloaded software without a model (Recipes, ADR 0018):
  recipe plan FILE                  which recipe fits, and the suggested answers (JSON)
  recipe build FILE [--name N] [--version V] [--program P] [--description D]
               [--free|--unfree] [--menu|--no-menu] [--keep-source|--no-keep-source]
                                    build and try the package as you; prints the result
                                    (JSON) for `addLocalPackage`; the build log goes to stderr
  recipe install RESULT.json        install what `recipe build` printed (asks for authorization)
  recipe ops RESULT.json            the changes `recipe install` would make, as JSON
  recipe check FILE                 what TulsiOS refuses in a package.nix (JSON list)
  recipe build-draft DIR            build and try a draft as edited (DIR holds package.nix
                                    and recipe.json); prints the result like `recipe build`
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
        ["keep-source", name, setting @ ("on" | "off")] => {
            vec![Op::KeepSource {
                name: name.to_string(),
                keep: *setting == "on",
            }]
        }
        ["service", action @ ("enable" | "disable"), name] => {
            vec![Op::SetService {
                name: name.to_string(),
                enable: *action == "enable",
            }]
        }
        ["upgrade"] if opts.dry_run => return check_upgrade(false).await,
        ["upgrade"] => return upgrade(opts).await,
        ["upgrade", "--check"] => return check_upgrade(false).await,
        ["upgrade", "--check", "--notify"] | ["upgrade", "--notify", "--check"] => {
            return check_upgrade(true).await
        }
        ["undo" | "rollback"] => return undo(opts, None).await,
        ["undo" | "rollback", commit] => return undo(opts, Some(commit)).await,
        ["search", words @ ..] if !words.is_empty() => return search(&words.join(" ")).await,
        ["match", "--tool", tool, names @ ..] if !names.is_empty() => {
            return match_names(tool, names).await
        }
        ["match", names @ ..] if !names.is_empty() => return match_names("", names).await,
        ["recipe", "plan", file] => {
            let plan = recipe_plan(Path::new(file)).await;
            out!(
                "{}",
                serde_json::to_string_pretty(&plan).expect("plan serializes")
            );
            return Ok(ExitCode::SUCCESS);
        }
        ["recipe", "build", file, flags @ ..] => return recipe_build(Path::new(file), flags).await,
        ["recipe", "install", result] => recipe_install_ops(Path::new(result))?,
        ["recipe", "ops", result] => {
            let ops = recipe_install_ops(Path::new(result))?;
            out!(
                "{}",
                serde_json::to_string_pretty(&ops).expect("ops serialize")
            );
            return Ok(ExitCode::SUCCESS);
        }
        ["recipe", "check", file] => {
            let text = std::fs::read_to_string(file).map_err(|e| format!("{file}: {e}"))?;
            let problems = tulsi_state::check_expression(&text);
            out!(
                "{}",
                serde_json::to_string_pretty(&problems).expect("problems serialize")
            );
            return Ok(if problems.is_empty() {
                ExitCode::SUCCESS
            } else {
                ExitCode::FAILURE
            });
        }
        ["recipe", "build-draft", dir] => {
            let outcome =
                tulsi_recipes::build_draft(Path::new(dir), &mut |line| eprintln!("{line}"));
            out!(
                "{}",
                serde_json::to_string_pretty(&outcome).expect("outcome serializes")
            );
            return Ok(if outcome.ok {
                ExitCode::SUCCESS
            } else {
                ExitCode::FAILURE
            });
        }
        ["inspect", file] => {
            let found = tulsi_inspect::inspect(Path::new(file));
            out!(
                "{}",
                serde_json::to_string_pretty(&found).expect("inspection serializes")
            );
            return Ok(ExitCode::SUCCESS);
        }
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
            if let Some(v) = tulsios_version() {
                out!("TulsiOS {v}");
            }
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

async fn undo(opts: &Options, commit: Option<&str>) -> Result<ExitCode, String> {
    let proxy = proxy().await?;
    let commit = match commit {
        Some(c) => c.to_string(),
        None => {
            let latest: Vec<HistoryEntry> =
                serde_json::from_str(&proxy.history(1).await.map_err(dbus)?)
                    .map_err(|e| format!("bad reply from tulsid: {e}"))?;
            latest
                .into_iter()
                .next()
                .ok_or("there is no change to undo")?
                .commit
        }
    };
    let plan: UndoPlan = serde_json::from_str(&proxy.plan_undo(&commit).await.map_err(dbus)?)
        .map_err(|e| format!("bad reply from tulsid: {e}"))?;
    out!(
        "Undo {} ({}):",
        plan.summary.trim_start_matches("tulsi: "),
        plan.commit
    );
    for line in &plan.changes {
        out!("{line}");
    }
    if opts.dry_run {
        return Ok(ExitCode::SUCCESS);
    }
    let proxy_ref = &proxy;
    let commit = commit.as_str();
    run_job(opts, proxy_ref, || async move {
        proxy_ref.undo_change(commit).await
    })
    .await
}

async fn fetch_upgrade_info(proxy: &ManagerProxy<'_>) -> Result<UpgradeInfo, String> {
    serde_json::from_str(&proxy.check_upgrade().await.map_err(dbus)?)
        .map_err(|e| format!("bad reply from tulsid: {e}"))
}

fn print_upgrade_info(info: &UpgradeInfo) {
    let short = |rev: &str| rev.chars().take(12).collect::<String>();
    out!(
        "TulsiOS {} ({})",
        info.current_version,
        short(&info.current_rev)
    );
    if !info.following.is_empty() {
        out!("follows {}", info.following);
    }
    if !info.error.is_empty() {
        out!("cannot check for a newer release: {}", info.error);
    } else if info.available {
        out!(
            "TulsiOS {} is available ({}): run `tulsi upgrade`",
            info.available_version,
            short(&info.available_rev)
        );
    } else {
        out!("This is the newest release.");
    }
}

async fn upgrade(opts: &Options) -> Result<ExitCode, String> {
    let proxy = proxy().await?;
    let proxy_ref = &proxy;
    run_job(opts, proxy_ref, || async move { proxy_ref.upgrade().await }).await
}

/// `tulsi upgrade --check [--notify]`. With --notify (the daily user timer), a
/// newer release is announced once, as a notification whose Upgrade button opens
/// the Software Center's Updates page.
async fn check_upgrade(notify: bool) -> Result<ExitCode, String> {
    let info = fetch_upgrade_info(&proxy().await?).await?;
    print_upgrade_info(&info);
    if notify && info.available && info.error.is_empty() {
        notify_upgrade(&info).await;
    }
    Ok(ExitCode::SUCCESS)
}

const UPGRADE_ACTION: &str = "upgrade";

/// Where the last announced release is remembered, so each one is announced once.
fn notified_path() -> Option<std::path::PathBuf> {
    let base = std::env::var_os("XDG_STATE_HOME")
        .map(std::path::PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|h| Path::new(&h).join(".local/state")))?;
    Some(base.join("tulsi/notified-upgrade"))
}

async fn notify_upgrade(info: &UpgradeInfo) {
    let remembered = notified_path();
    if let Some(path) = &remembered {
        if std::fs::read_to_string(path).is_ok_and(|r| r.trim() == info.available_rev) {
            return;
        }
    }
    let sent = async {
        let conn = zbus::Connection::session().await?;
        let notifications = tulsi_client::NotificationsProxy::new(&conn).await?;
        let mut clicks = notifications.receive_action_invoked().await?;
        let body = format!(
            "TulsiOS {} is available (you have {}). Upgrading keeps your apps and \
             settings, and you can undo it in the Software Center.",
            info.available_version, info.current_version
        );
        let id = notifications
            .notify(
                "TulsiOS",
                0,
                "system-software-update",
                &format!("TulsiOS {} is available", info.available_version),
                &body,
                &[UPGRADE_ACTION, "Upgrade…"],
                std::collections::HashMap::new(),
                0,
            )
            .await?;
        if let Some(path) = &remembered {
            if let Some(dir) = path.parent() {
                let _ = std::fs::create_dir_all(dir);
            }
            let _ = std::fs::write(path, &info.available_rev);
        }
        // Wait a while for the button; the notification stays in the tray after that.
        let clicked = tokio::time::timeout(std::time::Duration::from_secs(3600), async {
            while let Some(signal) = clicks.next().await {
                if let Ok(args) = signal.args() {
                    if args.id == id && args.action_key == UPGRADE_ACTION {
                        return true;
                    }
                }
            }
            false
        })
        .await
        .unwrap_or(false);
        if clicked {
            let _ = std::process::Command::new("ocimum-software-center")
                .arg("--upgrade")
                .spawn();
        }
        zbus::Result::Ok(())
    }
    .await;
    if let Err(e) = sent {
        eprintln!("tulsi: cannot show a notification: {e}");
    }
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

/// The recipe plan for `file`; a suggested name TulsiOS already uses for one of its
/// own packages gets `-download` added (local packages cannot shadow those).
async fn recipe_plan(file: &Path) -> tulsi_recipes::Plan {
    let mut plan = tulsi_recipes::plan(&tulsi_inspect::inspect(file));
    if let Ok(proxy) = proxy().await {
        if let Ok(info) = proxy.package_info(&plan.name).await {
            let taken = serde_json::from_str::<PackageInfo>(&info).is_ok_and(|i| !i.local);
            if taken {
                plan.name = format!("{}-download", plan.name);
            }
        }
    }
    plan
}

/// The ops that install what `recipe build` printed (saved to `result`): accepting
/// its licence if it is proprietary, and adding it as a local package.
fn recipe_install_ops(result: &Path) -> Result<Vec<Op>, String> {
    let text = std::fs::read_to_string(result)
        .map_err(|e| format!("cannot read {}: {e}", result.display()))?;
    let v: serde_json::Value =
        serde_json::from_str(&text).map_err(|e| format!("{}: {e}", result.display()))?;
    if v["ok"] != serde_json::Value::Bool(true) {
        return Err(format!(
            "that build did not succeed: {}",
            v["error"].as_str().unwrap_or("")
        ));
    }
    let s = |k: &str| v[k].as_str().unwrap_or_default().to_string();
    let name = s("name");
    let mut ops = Vec::new();
    if v["unfree"] == serde_json::Value::Bool(true) {
        ops.push(Op::AcceptLicense { name: name.clone() });
    }
    ops.push(Op::AddLocalPackage {
        name,
        expression: s("expression"),
        version: s("version"),
        description: s("description"),
        origin: s("origin"),
        keep_source: v["keepSource"] != serde_json::Value::Bool(false),
    });
    Ok(ops)
}

async fn recipe_build(file: &Path, flags: &[&str]) -> Result<ExitCode, String> {
    let plan = recipe_plan(file).await;
    let mut answers = tulsi_recipes::Answers {
        name: plan.name.clone(),
        version: plan.version.clone(),
        program: plan.program.clone(),
        unfree: plan.license == "unfree",
        menu: plan.menu,
        keep_source: true,
        ..Default::default()
    };
    let mut it = flags.iter();
    while let Some(flag) = it.next() {
        let mut value = || {
            it.next()
                .map(|v| v.to_string())
                .ok_or(format!("{flag} needs a value"))
        };
        match *flag {
            "--name" => answers.name = value()?,
            "--version" => answers.version = value()?,
            "--program" => answers.program = value()?,
            "--description" => answers.description = value()?,
            "--unfree" => answers.unfree = true,
            "--free" => answers.unfree = false,
            "--menu" => answers.menu = true,
            "--no-menu" => answers.menu = false,
            "--keep-source" => answers.keep_source = true,
            "--no-keep-source" => answers.keep_source = false,
            other => return Err(format!("unknown option {other}")),
        }
    }
    let outcome = tulsi_recipes::build(file, &plan, &answers, &mut |line| eprintln!("{line}"));
    out!(
        "{}",
        serde_json::to_string_pretty(&outcome).expect("outcome serializes")
    );
    Ok(if outcome.ok {
        ExitCode::SUCCESS
    } else {
        ExitCode::FAILURE
    })
}

async fn match_names(tool: &str, names: &[&str]) -> Result<ExitCode, String> {
    let hint = MatchHint {
        names: names.iter().map(|n| n.to_string()).collect(),
        tool: tool.to_string(),
        ..Default::default()
    };
    let hint = serde_json::to_string(&hint).expect("hint serializes");
    let found: Vec<Candidate> =
        serde_json::from_str(&proxy().await?.match_(&hint, 10).await.map_err(dbus)?)
            .map_err(|e| format!("bad reply from tulsid: {e}"))?;
    if found.is_empty() {
        out!("Nothing in TulsiOS matches {}.", names.join(" "));
    }
    for c in found {
        match c {
            Candidate::Package { info, reason } => {
                let mark = if info.installed { '*' } else { ' ' };
                out!("{mark} {:<32} {reason}", info.attr);
            }
            Candidate::Service {
                name,
                enabled,
                reason,
            } => {
                let mark = if enabled { '*' } else { ' ' };
                out!(
                    "{mark} {:<32} {reason} (tulsi service enable {name})",
                    format!("service {name}")
                );
            }
        }
    }
    Ok(ExitCode::SUCCESS)
}

async fn history(n: u32) -> Result<ExitCode, String> {
    let entries: Vec<HistoryEntry> =
        serde_json::from_str(&proxy().await?.history(n).await.map_err(dbus)?)
            .map_err(|e| format!("bad reply from tulsid: {e}"))?;
    for e in entries {
        let by = match e.by.strip_prefix("starah-") {
            Some(agent) => format!("  (agent {agent})"),
            None if !e.by.is_empty() => format!("  ({})", e.by),
            None => String::new(),
        };
        out!("{}  {}  {}{by}", e.commit, format_time(e.time), e.summary);
    }
    Ok(ExitCode::SUCCESS)
}

/// The running TulsiOS release, from /etc/os-release (`TULSIOS_VERSION`).
fn tulsios_version() -> Option<String> {
    let text = std::fs::read_to_string("/etc/os-release").ok()?;
    text.lines().find_map(|l| {
        l.strip_prefix("TULSIOS_VERSION=")
            .map(|v| v.trim_matches('"').to_string())
    })
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
