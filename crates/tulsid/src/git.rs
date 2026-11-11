//! Git history of the system flake directory. tulsid only ever commits the
//! files it manages (`tulsi/state.json`, `configuration.nix`, `flake.lock`);
//! anything else the user changes is left alone.

use std::path::Path;

use tokio::process::Command;
use tulsi_client::HistoryEntry;
use tulsi_state::State;

use crate::config::Config;

/// Files whose changes make up tulsid's history.
pub const MANAGED: [&str; 2] = [Config::STATE_REL, Config::CONFIG_REL];

/// A managed file's contents before and after a change (`None` = absent).
#[derive(Debug, Clone)]
pub struct FileChange {
    pub rel: &'static str,
    pub old: Option<Vec<u8>>,
    pub new: Option<Vec<u8>>,
}

pub async fn git(dir: &Path, args: &[&str]) -> Result<String, String> {
    let out = Command::new("git")
        .arg("-C")
        .arg(dir)
        .args([
            "-c",
            "user.name=tulsid",
            "-c",
            "user.email=tulsid@localhost",
            "-c",
            "commit.gpgsign=false",
        ])
        .args(args)
        .output()
        .await
        .map_err(|e| format!("cannot run git: {e}"))?;
    if out.status.success() {
        Ok(String::from_utf8_lossy(&out.stdout).into_owned())
    } else {
        Err(format!(
            "git {} failed: {}",
            args.join(" "),
            String::from_utf8_lossy(&out.stderr).trim()
        ))
    }
}

/// Makes sure `<flakeDir>` is a git repo with a committed state file.
pub async fn init_repo(cfg: &Config) -> Result<(), String> {
    let dir = &cfg.flake_dir;
    let state_path = cfg.state_path();
    std::fs::create_dir_all(state_path.parent().unwrap())
        .map_err(|e| format!("cannot create {}: {e}", dir.display()))?;

    if !state_path.exists() {
        let initial = match &cfg.initial_state {
            Some(path) => State::load(path).map_err(|e| e.to_string())?,
            None => State::default(),
        };
        write_atomic(&state_path, initial.to_json_pretty().as_bytes())?;
        eprintln!("tulsid: created {}", state_path.display());
    } else if let Err(e) = State::load(&state_path) {
        // Keep running so the problem is visible through the API.
        eprintln!("tulsid: warning: {e}");
    }

    if !dir.join(".git").exists() {
        git(dir, &["init", "-q"]).await?;
        git(dir, &["add", "-A"]).await?;
        git(
            dir,
            &[
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                "tulsi: initial state",
            ],
        )
        .await?;
        eprintln!("tulsid: initialized git history in {}", dir.display());
    } else {
        git(dir, &["add", "--", Config::STATE_REL]).await?;
        let staged = git(
            dir,
            &["diff", "--cached", "--name-only", "--", Config::STATE_REL],
        )
        .await?;
        if !staged.trim().is_empty() {
            commit(dir, "tulsi: track state", &[Config::STATE_REL]).await?;
        }
    }
    Ok(())
}

pub fn read(dir: &Path, rel: &str) -> Option<Vec<u8>> {
    std::fs::read(dir.join(rel)).ok()
}

/// Writes (or deletes, for `None`) a managed file and stages it, because
/// flakes only see files git knows about.
pub async fn put(dir: &Path, rel: &str, contents: Option<&[u8]>) -> Result<(), String> {
    let path = dir.join(rel);
    match contents {
        Some(bytes) => {
            write_atomic(&path, bytes)?;
            git(dir, &["add", "--", rel]).await.map(|_| ())
        }
        None => {
            if path.exists() {
                std::fs::remove_file(&path)
                    .map_err(|e| format!("cannot remove {}: {e}", path.display()))?;
            }
            // Unlike `git add`, this also works if git never knew the file.
            git(
                dir,
                &["rm", "-q", "--cached", "--ignore-unmatch", "--", rel],
            )
            .await
            .map(|_| ())
        }
    }
}

pub fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("cannot create {}: {e}", parent.display()))?;
    }
    let mut tmp = path.as_os_str().to_owned();
    tmp.push(".tmp");
    let tmp = std::path::PathBuf::from(tmp);
    std::fs::write(&tmp, bytes).map_err(|e| format!("cannot write {}: {e}", tmp.display()))?;
    std::fs::rename(&tmp, path).map_err(|e| format!("cannot replace {}: {e}", path.display()))
}

/// Commits `paths` (plus `flake.lock` when present: the first rebuild
/// creates it) and returns the short commit hash.
pub async fn commit(dir: &Path, message: &str, paths: &[&str]) -> Result<String, String> {
    let mut paths: Vec<&str> = paths.to_vec();
    if dir.join("flake.lock").exists() {
        paths.push("flake.lock");
        git(dir, &["add", "--", "flake.lock"]).await?;
    }
    // The managed files are already staged by `put` (including deletions).
    let mut commit = vec!["commit", "-q", "-m", message, "--"];
    commit.extend(&paths);
    git(dir, &commit).await?;
    Ok(git(dir, &["rev-parse", "--short", "HEAD"])
        .await?
        .trim()
        .to_string())
}

pub async fn history(dir: &Path, limit: u32) -> Result<Vec<HistoryEntry>, String> {
    let n = format!("-n{}", limit.max(1));
    let mut args = vec!["log", &n, "--format=%h%x1f%ct%x1f%s", "--"];
    args.extend(MANAGED);
    let out = git(dir, &args).await?;
    Ok(out
        .lines()
        .filter_map(|line| {
            let mut parts = line.splitn(3, '\x1f');
            Some(HistoryEntry {
                commit: parts.next()?.to_string(),
                time: parts.next()?.parse().ok()?,
                summary: parts.next()?.to_string(),
            })
        })
        .collect())
}

/// What undoing the most recent change means: for each managed file it
/// touched, the version before it. Also returns that change's summary.
pub async fn undo_changes(dir: &Path) -> Result<(Vec<FileChange>, String), String> {
    let mut args = vec!["log", "-n1", "--format=%H%x1f%s", "--"];
    args.extend(MANAGED);
    let last = git(dir, &args).await?;
    let (hash, summary) = last.trim().split_once('\x1f').ok_or("no history to undo")?;
    if git(dir, &["rev-parse", "--verify", "-q", &format!("{hash}^")])
        .await
        .is_err()
    {
        return Err(format!("nothing to undo before \"{summary}\""));
    }

    let mut args = vec!["show", "--name-only", "--format=", hash, "--"];
    args.extend(MANAGED);
    let touched = git(dir, &args).await?;
    let mut changes = Vec::new();
    for rel in MANAGED {
        if !touched.lines().any(|l| l.trim() == rel) {
            continue;
        }
        let before = git(dir, &["show", &format!("{hash}^:{rel}")])
            .await
            .ok()
            .map(String::into_bytes);
        changes.push(FileChange {
            rel,
            old: read(dir, rel),
            new: before,
        });
    }
    if changes.is_empty() {
        return Err(format!("nothing to undo in \"{summary}\""));
    }
    Ok((changes, summary.to_string()))
}
