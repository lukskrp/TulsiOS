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
use tulsi_client::{
    config_action, PackageInfo, Plan, ACTION_APPLY, ACTION_CONFIGURE, ACTION_EXTENSIONS,
    OBJECT_PATH,
};
use tulsi_state::{describe_all, Op, State};
use zbus::message::Header;
use zbus::object_server::SignalEmitter;
use zbus::{interface, Connection};

use crate::config::Config;
use crate::git::FileChange;
use crate::index::Index;
use crate::{git, localpkg, nixfile, polkit};

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
        // Local expressions are checked even without a package index.
        let lint: Vec<String> = ops
            .iter()
            .filter_map(|o| match o {
                Op::AddLocalPackage {
                    name, expression, ..
                } => Some(
                    localpkg::check_expression(expression)
                        .into_iter()
                        .map(move |p| format!("local package \"{name}\": {p}")),
                ),
                _ => None,
            })
            .flatten()
            .collect();
        if !lint.is_empty() {
            return Err(TulsiError::Invalid(lint.join("\n")));
        }
        let Some(index) = self.index.as_deref() else {
            return Ok(());
        };
        let mut problems = Vec::new();
        let current = self.current_state().ok();
        let accepted = current
            .as_ref()
            .map(|s| s.accepted_licenses.clone())
            .unwrap_or_default();
        let local_now = current.map(|s| s.local_packages).unwrap_or_default();
        let local_names: Vec<&str> = ops
            .iter()
            .filter_map(|o| match o {
                Op::AddLocalPackage { name, .. } => Some(name.as_str()),
                _ => None,
            })
            .collect();
        for op in ops {
            if let Op::AddLocalPackage {
                name, expression, ..
            } = op
            {
                if index.get(name).is_some() {
                    problems.push(format!(
                        "\"{name}\" is already in the Software Center; install it from there, \
                         or give the local package another name"
                    ));
                }
                let _ = expression; // checked at the top
                continue;
            }
            if let Op::AcceptLicense { name } = op {
                let local = local_names.contains(&name.as_str()) || local_now.contains(name);
                if !local && !self.cfg.unfree_agents.contains_key(name.as_str()) {
                    problems.push(format!(
                        "the licence of \"{name}\" cannot be accepted here: it is not one of                          the unfree packages TulsiOS allows (tulsi.daemon.unfreeAgents)"
                    ));
                }
                continue;
            }
            let Op::AddPackage { name } = op else {
                continue;
            };
            if name.contains('.')
                || local_now.contains(name)
                || local_names.contains(&name.as_str())
            {
                continue;
            }
            let licence_ok = |name: &str| {
                accepted.iter().any(|a| a == name)
                    || ops
                        .iter()
                        .any(|o| matches!(o, Op::AcceptLicense { name: n } if n == name))
            };
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
                Some(info) if info.unfree && !self.cfg.allow_unfree => {
                    match self.cfg.unfree_agents.get(name.as_str()) {
                        Some(_) if licence_ok(name) => {}
                        Some(l) => problems.push(format!(
                            "\"{name}\" is unfree: a person must accept its licence first                              ({}{}). In the Software Center, installing it asks for this.",
                            l.name,
                            if l.url.is_empty() { String::new() } else { format!(", {}", l.url) }
                        )),
                        None => problems.push(format!(
                            "\"{name}\" is unfree; enable nixpkgs.config.allowUnfree to install it"
                        )),
                    }
                }
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
        let state = self.current_state().ok();
        for info in &mut infos {
            if let Some(state) = &state {
                info.installed = state.packages.contains(&info.attr);
                info.license_accepted = state.accepted_licenses.contains(&info.attr);
            }
            if info.unfree && !self.cfg.allow_unfree {
                info.license = self.cfg.unfree_agents.get(info.attr.as_str()).cloned();
            }
        }
        infos
    }

    /// The file changes for local-package ops (expression and meta.json).
    fn local_package_changes(&self, ops: &[Op]) -> Vec<FileChange> {
        let dir = &self.cfg.flake_dir;
        let mut changes = Vec::new();
        for op in ops {
            match op {
                Op::AddLocalPackage {
                    name,
                    expression,
                    version,
                    description,
                    origin,
                } => changes.extend(localpkg::add_changes(
                    dir,
                    name,
                    expression,
                    &localpkg::Meta {
                        version: version.clone(),
                        description: description.clone(),
                        origin: origin.clone(),
                    },
                )),
                Op::RemoveLocalPackage { name } => {
                    changes.extend(localpkg::remove_changes(dir, name))
                }
                _ => {}
            }
        }
        changes
    }

    /// Local packages as PackageInfo, optionally only those matching `query`.
    fn local_infos(&self, query: Option<&str>) -> Vec<PackageInfo> {
        let Ok(state) = self.current_state() else {
            return Vec::new();
        };
        let words: Vec<String> = query
            .map(|q| {
                q.to_lowercase()
                    .split_whitespace()
                    .map(str::to_string)
                    .collect()
            })
            .unwrap_or_default();
        state
            .local_packages
            .iter()
            .filter_map(|name| {
                let meta = localpkg::read_meta(&self.cfg.flake_dir, name);
                let hay = format!("{name} {}", meta.description).to_lowercase();
                if !words.iter().all(|w| hay.contains(w.as_str())) {
                    return None;
                }
                Some(PackageInfo {
                    attr: name.clone(),
                    pname: name.clone(),
                    version: meta.version,
                    description: meta.description,
                    unfree: false,
                    installed: state.packages.contains(name),
                    license: None,
                    license_accepted: state.accepted_licenses.contains(name),
                    local: true,
                    origin: meta.origin,
                })
            })
            .collect()
    }

    /// Licences are accepted by people. Starah agents (system users `starah-*`, see
    /// ADR 0011) may install an agent whose licence was accepted, never accept one.
    async fn refuse_agent_licence(
        &self,
        conn: &Connection,
        hdr: &Header<'_>,
        ops: &[Op],
    ) -> Result<()> {
        if !ops.iter().any(|o| matches!(o, Op::AcceptLicense { .. })) {
            return Ok(());
        }
        let sender = hdr
            .sender()
            .ok_or_else(|| TulsiError::NotAuthorized("message has no sender".into()))?;
        let dbus = zbus::fdo::DBusProxy::new(conn).await?;
        let uid = dbus
            .get_connection_unix_user(sender.clone().into())
            .await
            .map_err(|e| TulsiError::Failed(e.to_string()))?;
        if user_name(uid).is_some_and(|u| u.starts_with("starah-")) {
            return Err(TulsiError::NotAuthorized(
                "an AI agent cannot accept a software licence; a person has to, in the                  Software Center"
                    .into(),
            ));
        }
        Ok(())
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

    /// A state.json change as a file change.
    fn state_change(old: &State, new: &State) -> FileChange {
        FileChange {
            rel: Config::STATE_REL.to_string(),
            old: Some(old.to_json_pretty().into_bytes()),
            new: Some(new.to_json_pretty().into_bytes()),
        }
    }

    /// Starts the transaction in the background and returns its job id. `action` is
    /// the polkit action the change was authorized with; the commit records it.
    fn start_job(
        &self,
        guard: OwnedMutexGuard<()>,
        conn: &Connection,
        changes: Vec<FileChange>,
        message: String,
        action: &str,
    ) -> Result<u64> {
        let job = self.next_job.fetch_add(1, Ordering::Relaxed);
        let emitter = SignalEmitter::new(conn, OBJECT_PATH)?.into_owned();
        let cfg = self.cfg.clone();
        let commit_message = git::commit_message(&message, action);
        tokio::spawn(async move {
            let _guard = guard;
            eprintln!("tulsid: job {job}: {message}");
            let result = run_transaction(&cfg, &emitter, job, &changes, &commit_message).await;
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
        self.refuse_agent_licence(conn, &hdr, &ops).await?;
        self.authorize(conn, &hdr, required_action(&ops)).await?;
        let guard = self.try_lock()?;
        let old = self.current_state()?;
        let new = old.with_ops(&ops)?;
        let mut changes = self.local_package_changes(&ops);
        if old.diff(&new).is_empty() && changes.is_empty() {
            return Ok(0);
        }
        changes.insert(0, Self::state_change(&old, &new));
        self.start_job(
            guard,
            conn,
            changes,
            format!("tulsi: {}", describe_all(&ops)),
            required_action(&ops),
        )
    }

    /// Reverts the most recent change (itself recorded as a new change). Needs the
    /// polkit action that change needed.
    async fn undo(
        &self,
        #[zbus(header)] hdr: Header<'_>,
        #[zbus(connection)] conn: &Connection,
    ) -> Result<u64> {
        let latest = git::history(&self.cfg.flake_dir, 1)
            .await
            .map_err(TulsiError::Failed)?;
        let latest = latest
            .first()
            .ok_or_else(|| TulsiError::Invalid("no history to undo".into()))?;
        let action = undo_action(latest.action());
        self.authorize(conn, &hdr, action).await?;
        let guard = self.try_lock()?;
        let still_latest = git::history(&self.cfg.flake_dir, 1)
            .await
            .map_err(TulsiError::Failed)?;
        if still_latest.first().map(|e| &e.commit) != Some(&latest.commit) {
            return Err(TulsiError::Busy(
                "the history changed meanwhile; try again".into(),
            ));
        }
        let (changes, summary) = git::undo_changes(&self.cfg.flake_dir)
            .await
            .map_err(TulsiError::Invalid)?;
        // Never restore a state file tulsid could not read back.
        for change in &changes {
            if change.rel == Config::STATE_REL {
                let text = String::from_utf8_lossy(change.new.as_deref().unwrap_or_default());
                State::from_json(&text)?;
            }
        }
        let summary = summary
            .strip_prefix("tulsi: ")
            .unwrap_or(&summary)
            .to_string();
        self.start_job(
            guard,
            conn,
            changes,
            format!("tulsi: undo {summary}"),
            action,
        )
    }

    /// The current configuration.nix ("" if it does not exist).
    async fn get_config(&self) -> Result<String> {
        let bytes = git::read(&self.cfg.flake_dir, Config::CONFIG_REL).unwrap_or_default();
        String::from_utf8(bytes)
            .map_err(|_| TulsiError::Failed("configuration.nix is not UTF-8".into()))
    }

    /// Checks proposed configuration.nix contents and returns
    /// `{"changed": bool, "diff": "<unified diff>"}`. Nothing is written.
    async fn plan_config(&self, contents: &str) -> Result<String> {
        nixfile::check_syntax(contents)
            .await
            .map_err(TulsiError::Invalid)?;
        let old = git::read(&self.cfg.flake_dir, Config::CONFIG_REL);
        let diff = nixfile::diff(Config::CONFIG_REL, old.as_deref(), contents.as_bytes())
            .await
            .map_err(TulsiError::Failed)?;
        Ok(serde_json::json!({ "changed": !diff.is_empty(), "diff": diff }).to_string())
    }

    /// Replaces configuration.nix and rebuilds; restores it if the rebuild
    /// fails. Returns a job id (0 if nothing changed).
    async fn apply_config(
        &self,
        #[zbus(header)] hdr: Header<'_>,
        #[zbus(connection)] conn: &Connection,
        contents: &str,
        summary: &str,
    ) -> Result<u64> {
        nixfile::check_syntax(contents)
            .await
            .map_err(TulsiError::Invalid)?;
        let summary = one_line(summary);
        if summary.is_empty() {
            return Err(TulsiError::Invalid(
                "a short summary of the edit is required".into(),
            ));
        }
        let before = git::read(&self.cfg.flake_dir, Config::CONFIG_REL);
        let (action, _) = config_action(
            &String::from_utf8_lossy(before.as_deref().unwrap_or_default()),
            contents,
        );
        self.authorize(conn, &hdr, action).await?;
        let guard = self.try_lock()?;
        let old = git::read(&self.cfg.flake_dir, Config::CONFIG_REL);
        if old != before {
            // Authorized for the edit against `before`, not against this file.
            return Err(TulsiError::Busy(
                "configuration.nix changed meanwhile; try again".into(),
            ));
        }
        if old.as_deref() == Some(contents.as_bytes()) {
            return Ok(0);
        }
        let change = FileChange {
            rel: Config::CONFIG_REL.to_string(),
            old,
            new: Some(contents.as_bytes().to_vec()),
        };
        self.start_job(
            guard,
            conn,
            vec![change],
            format!("tulsi: edit configuration.nix: {summary}"),
            action,
        )
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
        let mut results = self.local_infos(Some(query));
        results.extend(self.mark_installed(self.index()?.search(query, limit)));
        results.truncate(limit);
        Ok(serde_json::to_string(&results).expect("results serialize"))
    }

    /// Details of one package attribute, as JSON.
    async fn package_info(&self, attr: &str) -> Result<String> {
        if let Some(info) = self.local_infos(None).into_iter().find(|i| i.attr == attr) {
            return Ok(serde_json::to_string(&info).expect("info serializes"));
        }
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

/// Changes that only touch browser extensions use their own polkit action, which
/// the tulsi.browserExtensions module may allow without a password; adding a local
/// package uses org.tulsi.configure (see `tulsi_client::ops_action`).
fn required_action(ops: &[Op]) -> &'static str {
    tulsi_client::ops_action(ops)
}

/// The action undoing a change needs: the one it was made with. Anything not
/// recognised counts as the strictest.
fn undo_action(recorded: &str) -> &'static str {
    match recorded {
        ACTION_EXTENSIONS => ACTION_EXTENSIONS,
        ACTION_APPLY => ACTION_APPLY,
        _ => ACTION_CONFIGURE,
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

/// uid → user name, from /etc/passwd.
fn user_name(uid: u32) -> Option<String> {
    let passwd = std::fs::read_to_string("/etc/passwd").ok()?;
    passwd.lines().find_map(|line| {
        let mut f = line.split(':');
        let name = f.next()?;
        f.next()?;
        (f.next()?.parse::<u32>().ok()? == uid).then(|| name.to_string())
    })
}

/// Collapses a free-text summary into one short line for a commit message.
fn one_line(text: &str) -> String {
    let line: String = text.split_whitespace().collect::<Vec<_>>().join(" ");
    line.chars().take(120).collect()
}

/// The order to write `targets` (path, contents to write; `None` deletes) in, so
/// that state.json never names a local package whose files are missing: files
/// that are written come first, then state.json, then deletions.
fn write_order<'a>(targets: &[(&'a str, Option<&'a [u8]>)]) -> Vec<(&'a str, Option<&'a [u8]>)> {
    let rank = |&(rel, contents): &(&str, Option<&[u8]>)| match (rel == Config::STATE_REL, contents)
    {
        (false, Some(_)) => 0,
        (true, _) => 1,
        (false, None) => 2,
    };
    let mut ordered = targets.to_vec();
    ordered.sort_by_key(rank); // stable: keeps the order within each group
    ordered
}

/// Writes the new file versions, rebuilds, commits. On failure restores the
/// old versions. Returns the commit hash, or an error including the log tail.
async fn run_transaction(
    cfg: &Config,
    emitter: &SignalEmitter<'static>,
    job: u64,
    changes: &[FileChange],
    message: &str,
) -> std::result::Result<String, String> {
    let dir = &cfg.flake_dir;
    let applied = async {
        let targets: Vec<_> = changes
            .iter()
            .map(|c| (c.rel.as_str(), c.new.as_deref()))
            .collect();
        for (rel, contents) in write_order(&targets) {
            git::put(dir, rel, contents).await?;
        }
        rebuild(cfg, emitter, job).await
    }
    .await;

    match applied {
        Ok(()) => {
            let paths: Vec<&str> = changes.iter().map(|c| c.rel.as_str()).collect();
            git::commit(dir, message, &paths).await
        }
        Err(e) => {
            let mut problems = Vec::new();
            let targets: Vec<_> = changes
                .iter()
                .map(|c| (c.rel.as_str(), c.old.as_deref()))
                .collect();
            for (rel, contents) in write_order(&targets) {
                if let Err(re) = git::put(dir, rel, contents).await {
                    problems.push(re);
                }
            }
            if problems.is_empty() {
                Err(e)
            } else {
                Err(format!(
                    "{e}\nadditionally failed to restore: {}",
                    problems.join("; ")
                ))
            }
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
            "rebuild failed ({status}); the previous configuration was restored.\n{}",
            tail.join("\n")
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn state_json_is_written_after_new_files_and_before_deletions() {
        let pkg = b"{ stdenvNoCC }: stdenvNoCC.mkDerivation { }".as_slice();
        let state = b"{}".as_slice();
        let order = |t: &[(&'static str, Option<&'static [u8]>)]| -> Vec<&'static str> {
            write_order(t).into_iter().map(|(rel, _)| rel).collect()
        };
        // Adding: the package files exist before state.json names them.
        let add = [
            (Config::STATE_REL, Some(state)),
            ("tulsi/pkgs/frob/package.nix", Some(pkg)),
            ("tulsi/pkgs/frob/meta.json", Some(pkg)),
        ];
        assert_eq!(
            order(&add),
            [
                "tulsi/pkgs/frob/package.nix",
                "tulsi/pkgs/frob/meta.json",
                Config::STATE_REL
            ]
        );
        // Removing (also undo and rollback of an add): state.json stops naming them first.
        let remove = [
            ("tulsi/pkgs/frob/package.nix", None),
            (Config::STATE_REL, Some(state)),
            ("tulsi/pkgs/frob/meta.json", None),
        ];
        assert_eq!(
            order(&remove),
            [
                Config::STATE_REL,
                "tulsi/pkgs/frob/package.nix",
                "tulsi/pkgs/frob/meta.json"
            ]
        );
    }
}
