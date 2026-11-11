//! tulsi-extwatch: makes browser extensions declarative automatically.
//!
//! Runs in the user's session. When the user installs an extension from
//! addons.mozilla.org or the Chrome Web Store, it notices (by watching the
//! browser profiles), tells the user with a desktop notification that the
//! extension will be installed declaratively, and asks tulsid to add it to
//! state.json. From then on the browser policy installs and owns it.
//!
//! The notification offers "Keep it imperative" for a short grace period;
//! choosing it is remembered in $XDG_STATE_HOME/tulsi/extwatch.json.
//!
//! usage: tulsi-extwatch [--once] [--interval SECS] [--grace SECS] [--no-notify]

mod notify;
mod scan;

use std::collections::{BTreeSet, HashMap};
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::time::{Duration, SystemTime};

use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use tulsi_client::{ManagerProxy, Op, State};

use crate::notify::Notifier;
use crate::scan::Found;

struct Options {
    once: bool,
    interval: Duration,
    grace: Duration,
    notify: bool,
}

/// Choices that persist across runs.
#[derive(Debug, Default, Serialize, Deserialize)]
struct Memory {
    /// "browser:id" the user chose to keep imperative.
    #[serde(default)]
    keep_imperative: BTreeSet<String>,
}

#[tokio::main]
async fn main() -> ExitCode {
    let mut opts = Options {
        once: false,
        interval: Duration::from_secs(3),
        grace: Duration::from_secs(8),
        notify: true,
    };
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--once" => opts.once = true,
            "--no-notify" => opts.notify = false,
            "--interval" | "--grace" => {
                let Some(secs) = args.next().and_then(|v| v.parse().ok()) else {
                    eprintln!("tulsi-extwatch: {arg} needs a number of seconds");
                    return ExitCode::FAILURE;
                };
                let d = Duration::from_secs(secs);
                if arg == "--interval" {
                    opts.interval = d
                } else {
                    opts.grace = d
                }
            }
            "--version" => {
                println!("tulsi-extwatch {}", env!("CARGO_PKG_VERSION"));
                return ExitCode::SUCCESS;
            }
            other => {
                eprintln!("tulsi-extwatch: unknown argument {other:?}");
                return ExitCode::FAILURE;
            }
        }
    }
    match run(opts).await {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("tulsi-extwatch: {e}");
            ExitCode::FAILURE
        }
    }
}

struct Dirs {
    home: PathBuf,
    config: PathBuf,
    memory_file: PathBuf,
}

impl Dirs {
    fn from_env() -> Result<Self, String> {
        let home = PathBuf::from(std::env::var_os("HOME").ok_or("HOME is not set")?);
        let xdg = |var: &str, fallback: &str| {
            std::env::var_os(var)
                .map(PathBuf::from)
                .unwrap_or_else(|| home.join(fallback))
        };
        Ok(Self {
            config: xdg("XDG_CONFIG_HOME", ".config"),
            memory_file: xdg("XDG_STATE_HOME", ".local/state").join("tulsi/extwatch.json"),
            home,
        })
    }
}

async fn run(opts: Options) -> Result<(), String> {
    let dirs = Dirs::from_env()?;
    let mut memory = load_memory(&dirs.memory_file);
    let notifier = if opts.notify {
        Notifier::connect().await
    } else {
        Notifier::disabled()
    };

    // Extensions handled during this run, so a failure is not retried in a loop.
    let mut attempted: BTreeSet<String> = BTreeSet::new();
    let mut last_mtimes: HashMap<PathBuf, SystemTime> = HashMap::new();

    loop {
        let mtimes = mtimes(&scan::watched_files(&dirs.home, &dirs.config));
        if opts.once || mtimes != last_mtimes {
            match pass(&opts, &dirs, &notifier, &mut memory, &mut attempted).await {
                Ok(()) => last_mtimes = mtimes,
                // tulsid unavailable (e.g. still starting): try again later.
                Err(e) => eprintln!("tulsi-extwatch: {e}"),
            }
        }
        if opts.once {
            return Ok(());
        }
        tokio::time::sleep(opts.interval).await;
    }
}

fn mtimes(files: &[PathBuf]) -> HashMap<PathBuf, SystemTime> {
    files
        .iter()
        .filter_map(|f| Some((f.clone(), std::fs::metadata(f).ok()?.modified().ok()?)))
        .collect()
}

/// One scan: adopts every store-installed extension not yet in state.json.
async fn pass(
    opts: &Options,
    dirs: &Dirs,
    notifier: &Notifier,
    memory: &mut Memory,
    attempted: &mut BTreeSet<String>,
) -> Result<(), String> {
    let found = scan::scan(&dirs.home, &dirs.config);
    if found.is_empty() {
        return Ok(());
    }
    // Re-read remembered choices: they may have been changed by another
    // instance or by hand since the last pass.
    *memory = load_memory(&dirs.memory_file);
    let conn = tulsi_client::connect()
        .await
        .map_err(|e| format!("cannot connect to the system bus: {e}"))?;
    let tulsid = ManagerProxy::new(&conn).await.map_err(|e| e.to_string())?;
    let state = State::from_json(
        &tulsid
            .get_state()
            .await
            .map_err(|e| format!("tulsid: {e}"))?,
    )
    .map_err(|e| e.to_string())?;

    for ext in found {
        let key = ext.key();
        if is_managed(&state, &ext)
            || memory.keep_imperative.contains(&key)
            || attempted.contains(&key)
        {
            continue;
        }
        attempted.insert(key.clone());

        let grace = if opts.once {
            Duration::ZERO
        } else {
            opts.grace
        };
        if notifier.announce(&ext, grace).await == notify::Choice::KeepImperative {
            println!("{key}: kept imperative at the user's request");
            memory.keep_imperative.insert(key);
            save_memory(&dirs.memory_file, memory);
            continue;
        }

        match adopt(&tulsid, &ext).await {
            Ok(msg) => {
                println!("{key}: adopted ({msg})");
                notifier.done(&ext, None).await;
            }
            Err(e) => {
                eprintln!("{key}: not adopted: {e}");
                notifier.done(&ext, Some(&e)).await;
            }
        }
    }
    Ok(())
}

fn is_managed(state: &State, ext: &Found) -> bool {
    let list = match ext.browser {
        tulsi_client::Browser::Firefox => &state.browser_extensions.firefox,
        tulsi_client::Browser::Chromium => &state.browser_extensions.chromium,
    };
    list.contains(&ext.id)
}

/// Asks tulsid to add the extension and waits for the rebuild to finish.
async fn adopt(tulsid: &ManagerProxy<'_>, ext: &Found) -> Result<String, String> {
    let ops = vec![Op::AddExtension {
        browser: ext.browser,
        id: ext.id.clone(),
    }];
    let ops = serde_json::to_string(&ops).expect("ops serialize");

    let mut finished = tulsid.receive_finished().await.map_err(|e| e.to_string())?;
    let job = tulsid.apply(&ops).await.map_err(describe_error)?;
    if job == 0 {
        return Ok("already declarative".into());
    }
    while let Some(signal) = finished.next().await {
        let Ok(args) = signal.args() else { continue };
        if args.job == job {
            return if args.success {
                Ok(args.message.clone())
            } else {
                Err(args.message.clone())
            };
        }
    }
    Err("lost connection to tulsid".into())
}

fn describe_error(e: zbus::Error) -> String {
    match e {
        zbus::Error::MethodError(_, Some(msg), _) => msg,
        other => other.to_string(),
    }
}

fn load_memory(path: &Path) -> Memory {
    std::fs::read_to_string(path)
        .ok()
        .and_then(|t| serde_json::from_str(&t).ok())
        .unwrap_or_default()
}

fn save_memory(path: &Path, memory: &Memory) {
    if let Some(dir) = path.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    let text = serde_json::to_string_pretty(memory).expect("memory serializes");
    if let Err(e) = std::fs::write(path, text) {
        eprintln!("tulsi-extwatch: cannot save {}: {e}", path.display());
    }
}
