//! Git history of the system flake directory. Only `tulsi/state.json` is
//! ever committed by tulsid; anything else the user changes is left alone.

use std::path::Path;

use tokio::process::Command;
use tulsi_client::HistoryEntry;
use tulsi_state::State;

use crate::config::Config;

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
        write_state(&state_path, &initial)?;
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
            commit(dir, "tulsi: track state").await?;
        }
    }
    Ok(())
}

/// Atomically replaces the state file.
pub fn write_state(path: &Path, state: &State) -> Result<(), String> {
    write_atomic(path, state.to_json_pretty().as_bytes())
}

pub fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let tmp = path.with_extension("json.tmp");
    std::fs::write(&tmp, bytes).map_err(|e| format!("cannot write {}: {e}", tmp.display()))?;
    std::fs::rename(&tmp, path).map_err(|e| format!("cannot replace {}: {e}", path.display()))
}

/// Commits the state file only; returns the short commit hash.
/// Also includes `flake.lock` when present: the first rebuild creates it, and
/// flakes ignore files git does not know about.
pub async fn commit(dir: &Path, message: &str) -> Result<String, String> {
    let mut paths = vec![Config::STATE_REL];
    if dir.join("flake.lock").exists() {
        paths.push("flake.lock");
    }
    let mut add = vec!["add", "--"];
    add.extend(&paths);
    git(dir, &add).await?;
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
    let out = git(
        dir,
        &[
            "log",
            &n,
            "--format=%h%x1f%ct%x1f%s",
            "--",
            Config::STATE_REL,
        ],
    )
    .await?;
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

/// The state before the most recent change, and that change's summary.
pub async fn previous_state(dir: &Path) -> Result<(State, String), String> {
    let last = git(
        dir,
        &["log", "-n1", "--format=%H%x1f%s", "--", Config::STATE_REL],
    )
    .await?;
    let (hash, summary) = last.trim().split_once('\x1f').ok_or("no history to undo")?;
    let spec = format!("{hash}^:{}", Config::STATE_REL);
    let text = git(dir, &["show", &spec])
        .await
        .map_err(|_| format!("nothing to undo before \"{summary}\""))?;
    let state = State::from_json(&text).map_err(|e| e.to_string())?;
    Ok((state, summary.to_string()))
}
