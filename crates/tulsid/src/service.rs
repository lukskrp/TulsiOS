//! The `org.tulsi.Manager1` D-Bus interface and the change transaction.
//!
//! A change is: authorize (polkit) → apply ops to state → write state.json →
//! run the rebuild command (output streamed as `Progress` signals) → on
//! success commit to git, on failure restore the previous state.json.
//! Only one change runs at a time.

use std::collections::VecDeque;
use std::process::Stdio;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;
use tokio::sync::{mpsc, Mutex, OwnedMutexGuard};
use tulsi_client::{PackageInfo, Plan, ACTION_APPLY, ACTION_EXTENSIONS, OBJECT_PATH};
use tulsi_state::{describe_all, Op, State};
use zbus::message::Header;
use zbus::object_server::SignalEmitter;
use zbus::{interface, Connection};

use crate::config::Config;
use crate::index::Index;
use crate::{git, polkit};

/// Upper bound for `Search` results.
const MAX_SEARCH_RESULTS: u32 = 500;

/// Lines of rebuild output kept for the error message of a failed job.
const LOG_TAIL: usize = 25;

#[derive(Debug, zbus::DBusError)]
#[zbus(prefix = "org.tulsi.Error")]
pub enum TulsiError {
    #[zbus(error)]
    ZBus(zbus::Error),
    NotAuthorized(String),
    Busy(String),
    Invalid(String),
    NotFound(String),
    Unavailable(String),
    Failed(String),
}

impl From<tulsi_state::Error> for TulsiError {
    fn from(e: tulsi_state::Error) -> Self {
        TulsiError::Invalid(e.to_string())
    }
}

type Result<T> = std::result::Result<T, TulsiError>;

pub struct Manager {
    cfg: Arc<Config>,
    index: Option<Arc<Index>>,
    lock: Arc<Mutex<()>>,
    next_job: AtomicU64,
}

impl Manager {
    pub fn new(cfg: Config, index: Option<Index>) -> Self {
        Self {
            cfg: Arc::new(cfg),
            index: index.map(Arc::new),
            lock: Arc::new(Mutex::new(())),
            next_job: AtomicU64::new(1),
        }
    }

    fn current_state(&self) -> Result<State> {
        State::load(&self.cfg.state_path()).map_err(|e| TulsiError::Failed(e.to_string()))
    }

    fn index(&self) -> Result<&Index> {
        self.index
            .as_deref()
            .ok_or_else(|| TulsiError::Unavailable("no package index is configured".into()))
    }

    /// Rejects unknown or unfree (when not allowed) top-level packages before
    /// any rebuild. Nested attributes (e.g. python3Packages.x) are not all in
    /// the index, so those are left to the rebuild to check.
    fn check_packages(&self, ops: &[Op]) -> Result<()> {
        let Some(index) = self.index.as_deref() else {
            return Ok(());
        };
        let mut problems = Vec::new();
        for op in ops {
            let Op::AddPackage { name } = op else {
                continue;
            };
            if name.contains('.') {
                continue;
            }
            match index.get(name) {
                None => {
                    let hints = index.suggest(name, 3);
                    let hint = if hints.is_empty() {
                        String::new()
                    } else {
                        format!(" (did you mean: {}?)", hints.join(", "))
                    };
                    problems.push(format!("unknown package \"{name}\"{hint}"));
                }
                Some(info) if info.unfree && !self.cfg.allow_unfree => problems.push(format!(
                    "\"{name}\" is unfree; enable nixpkgs.config.allowUnfree to install it"
                )),
                Some(_) => {}
            }
        }
        if problems.is_empty() {
            Ok(())
        } else {
            Err(TulsiError::Invalid(problems.join("\n")))
        }
    }

    fn mark_installed(&self, mut infos: Vec<PackageInfo>) -> Vec<PackageInfo> {
        if let Ok(state) = self.current_state() {
            for info in &mut infos {
                info.installed = state.packages.contains(&info.attr);
            }
        }
        infos
    }

    async fn authorize(&self, conn: &Connection, hdr: &Header<'_>, action: &str) -> Result<()> {
        if !self.cfg.polkit {
            return Ok(());
        }
        let sender = hdr
            .sender()
            .ok_or_else(|| TulsiError::NotAuthorized("message has no sender".into()))?;
        if polkit::check(conn, sender.as_str(), action).await? {
            Ok(())
        } else {
            Err(TulsiError::NotAuthorized(format!(
                "not authorized for {action} (are you an administrator?)"
            )))
        }
    }

    fn try_lock(&self) -> Result<OwnedMutexGuard<()>> {
        self.lock
            .clone()
            .try_lock_owned()
            .map_err(|_| TulsiError::Busy("another change is in progress".into()))
    }

    /// Starts the transaction in the background and returns its job id.
    fn start_job(
        &self,
        guard: OwnedMutexGuard<()>,
        conn: &Connection,
        old: State,
        new: State,
        message: String,
    ) -> Result<u64> {
        let job = self.next_job.fetch_add(1, Ordering::Relaxed);
        let emitter = SignalEmitter::new(conn, OBJECT_PATH)?.into_owned();
        let cfg = self.cfg.clone();
        tokio::spawn(async move {
            let _guard = guard;
            eprintln!("tulsid: job {job}: {message}");
            let result = run_transaction(&cfg, &emitter, job, &old, &new, &message).await;
            let (success, text) = match result {
                Ok(commit) => (true, format!("{message} (commit {commit})")),
                Err(e) => (false, e),
            };
            eprintln!(
                "tulsid: job {job} {}: {text}",
                if success { "succeeded" } else { "failed" }
            );
            let _ = Manager::finished(&emitter, job, success, &text).await;
        });
        Ok(job)
    }
}

#[interface(name = "org.tulsi.Manager1")]
impl Manager {
    /// The current state.json contents.
    async fn get_state(&self) -> Result<String> {
        Ok(self.current_state()?.to_json_pretty())
    }

    /// What `ops` would change, without applying anything.
    async fn plan(&self, ops: &str) -> Result<String> {
        let ops = parse_ops(ops)?;
        self.check_packages(&ops)?;
        let old = self.current_state()?;
        let new = old.with_ops(&ops)?;
        let plan = Plan {
            changes: old.diff(&new),
            state: new,
        };
        Ok(serde_json::to_string(&plan).expect("plan serializes"))
    }

    /// Applies `ops`. Returns a job id (0 if there was nothing to change);
    /// watch `Progress` and `Finished` for that id.
    async fn apply(
        &self,
        #[zbus(header)] hdr: Header<'_>,
        #[zbus(connection)] conn: &Connection,
        ops: &str,
    ) -> Result<u64> {
        let ops = parse_ops(ops)?;
        self.check_packages(&ops)?;
        self.authorize(conn, &hdr, required_action(&ops)).await?;
        let guard = self.try_lock()?;
        let old = self.current_state()?;
        let new = old.with_ops(&ops)?;
        if old.diff(&new).is_empty() {
            return Ok(0);
        }
        self.start_job(
            guard,
            conn,
            old,
            new,
            format!("tulsi: {}", describe_all(&ops)),
        )
    }

    /// Reverts the most recent change (itself recorded as a new change).
    async fn undo(
        &self,
        #[zbus(header)] hdr: Header<'_>,
        #[zbus(connection)] conn: &Connection,
    ) -> Result<u64> {
        self.authorize(conn, &hdr, ACTION_APPLY).await?;
        let guard = self.try_lock()?;
        let old = self.current_state()?;
        let (new, summary) = git::previous_state(&self.cfg.flake_dir)
            .await
            .map_err(TulsiError::Invalid)?;
        let summary = summary
            .strip_prefix("tulsi: ")
            .unwrap_or(&summary)
            .to_string();
        self.start_job(guard, conn, old, new, format!("tulsi: undo {summary}"))
    }

    /// The latest `limit` changes as JSON, newest first.
    async fn history(&self, limit: u32) -> Result<String> {
        let entries = git::history(&self.cfg.flake_dir, limit)
            .await
            .map_err(TulsiError::Failed)?;
        Ok(serde_json::to_string(&entries).expect("history serializes"))
    }

    /// Packages matching `query`, best first, as JSON.
    async fn search(&self, query: &str, limit: u32) -> Result<String> {
        let limit = limit.clamp(1, MAX_SEARCH_RESULTS) as usize;
        let results = self.mark_installed(self.index()?.search(query, limit));
        Ok(serde_json::to_string(&results).expect("results serialize"))
    }

    /// Details of one package attribute, as JSON.
    async fn package_info(&self, attr: &str) -> Result<String> {
        let info = self
            .index()?
            .get(attr)
            .ok_or_else(|| TulsiError::NotFound(format!("no package \"{attr}\"")))?;
        let info = self.mark_installed(vec![info]).remove(0);
        Ok(serde_json::to_string(&info).expect("info serializes"))
    }

    #[zbus(property)]
    async fn busy(&self) -> bool {
        self.lock.try_lock().is_err()
    }

    #[zbus(signal)]
    async fn progress(emitter: &SignalEmitter<'_>, job: u64, line: &str) -> zbus::Result<()>;

    #[zbus(signal)]
    async fn finished(
        emitter: &SignalEmitter<'_>,
        job: u64,
        success: bool,
        message: &str,
    ) -> zbus::Result<()>;
}

/// Changes that only touch browser extensions use their own polkit action,
/// which the tulsi.browserExtensions module may allow without a password.
fn required_action(ops: &[Op]) -> &'static str {
    let extensions_only = ops
        .iter()
        .all(|op| matches!(op, Op::AddExtension { .. } | Op::RemoveExtension { .. }));
    if extensions_only {
        ACTION_EXTENSIONS
    } else {
        ACTION_APPLY
    }
}

fn parse_ops(ops: &str) -> Result<Vec<Op>> {
    let ops: Vec<Op> =
        serde_json::from_str(ops).map_err(|e| TulsiError::Invalid(format!("invalid ops: {e}")))?;
    if ops.is_empty() {
        return Err(TulsiError::Invalid("no operations given".into()));
    }
    Ok(ops)
}

/// Writes `new`, rebuilds, commits. On failure restores `old`.
/// Returns the commit hash, or an error message including the log tail.
async fn run_transaction(
    cfg: &Config,
    emitter: &SignalEmitter<'static>,
    job: u64,
    old: &State,
    new: &State,
    message: &str,
) -> std::result::Result<String, String> {
    let state_path = cfg.state_path();
    git::write_state(&state_path, new)?;
    // Flakes only see files known to git.
    git::git(&cfg.flake_dir, &["add", "--", Config::STATE_REL]).await?;

    match rebuild(cfg, emitter, job).await {
        Ok(()) => git::commit(&cfg.flake_dir, message).await,
        Err(e) => {
            let restored = git::write_state(&state_path, old)
                .and(Ok(()))
                .map_err(|re| format!("{e}\nadditionally failed to restore state: {re}"));
            let _ = git::git(&cfg.flake_dir, &["add", "--", Config::STATE_REL]).await;
            restored?;
            Err(e)
        }
    }
}

async fn rebuild(
    cfg: &Config,
    emitter: &SignalEmitter<'static>,
    job: u64,
) -> std::result::Result<(), String> {
    let (program, args) = cfg
        .rebuild_command
        .split_first()
        .expect("validated non-empty");
    let mut child = Command::new(program)
        .args(args)
        .current_dir(&cfg.flake_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true)
        .spawn()
        .map_err(|e| format!("cannot start {program}: {e}"))?;

    let (tx, mut rx) = mpsc::unbounded_channel::<String>();
    for stream in [
        child
            .stdout
            .take()
            .map(|s| Box::new(s) as Box<dyn tokio::io::AsyncRead + Unpin + Send>),
        child
            .stderr
            .take()
            .map(|s| Box::new(s) as Box<dyn tokio::io::AsyncRead + Unpin + Send>),
    ]
    .into_iter()
    .flatten()
    {
        let tx = tx.clone();
        tokio::spawn(async move {
            let mut lines = BufReader::new(stream).lines();
            while let Ok(Some(line)) = lines.next_line().await {
                if tx.send(line).is_err() {
                    break;
                }
            }
        });
    }
    drop(tx);

    let mut tail = VecDeque::with_capacity(LOG_TAIL);
    while let Some(line) = rx.recv().await {
        let _ = Manager::progress(emitter, job, &line).await;
        if tail.len() == LOG_TAIL {
            tail.pop_front();
        }
        tail.push_back(line);
    }

    let status = child.wait().await.map_err(|e| format!("rebuild: {e}"))?;
    if status.success() {
        Ok(())
    } else {
        let tail: Vec<String> = tail.into();
        Err(format!(
            "rebuild failed ({status}); state restored.\n{}",
            tail.join("\n")
        ))
    }
}
