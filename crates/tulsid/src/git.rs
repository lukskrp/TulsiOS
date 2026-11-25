//! Git history of the system flake directory. tulsid only ever commits the
//! files it manages (`tulsi/state.json`, `configuration.nix`, local packages under
//! `tulsi/pkgs/`, `flake.lock`); anything else the user changes is left alone.

use std::path::Path;

use tokio::process::Command;
use tulsi_client::HistoryEntry;
use tulsi_state::State;

use crate::config::Config;

/// Files (and the local-package directory) whose changes make up tulsid's history.
/// flake.lock is one since upgrades move it (ADR 0017): an upgrade is listed and can
/// be undone like any other change.
pub const MANAGED: [&str; 4] = [
    Config::STATE_REL,
    Config::CONFIG_REL,
    Config::PKGS_REL,
    Config::LOCK_REL,
];

fn is_managed(rel: &str) -> bool {
    rel == Config::STATE_REL
        || rel == Config::CONFIG_REL
        || rel == Config::LOCK_REL
        || rel.starts_with(&format!("{}/", Config::PKGS_REL))
}

/// A managed file's contents before and after a change (`None` = absent).
#[derive(Debug, Clone)]
pub struct FileChange {
    pub rel: String,
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
            // Folders left empty (a local package's tulsi/pkgs/NAME) go too.
            let mut parent = path.parent();
            while let Some(p) = parent.filter(|p| *p != dir && p.starts_with(dir)) {
                if std::fs::remove_dir(p).is_err() {
                    break; // not empty
                }
                parent = p.parent();
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

/// The commit message for a change: its summary, plus trailers naming the polkit
/// action it needed (undoing it needs the same one) and who asked for it.
pub fn commit_message(summary: &str, action: &str, by: &str) -> String {
    let mut message = format!("{summary}\n\n{}: {action}", tulsi_client::ACTION_TRAILER);
    if !by.is_empty() {
        message.push_str(&format!("\n{}: {by}", tulsi_client::BY_TRAILER));
    }
    message
}

/// `git log` format for [`HistoryEntry`]: fields end with \x1f, entries with \x1e
/// (trailer values end a line).
fn entry_format() -> String {
    format!(
        "--format=%h%x1f%ct%x1f%s%x1f%(trailers:key={},valueonly,separator=%x2C)%x1f\
         %(trailers:key={},valueonly,separator=%x2C)%x1e",
        tulsi_client::ACTION_TRAILER,
        tulsi_client::BY_TRAILER
    )
}

pub async fn history(dir: &Path, limit: u32) -> Result<Vec<HistoryEntry>, String> {
    let n = format!("-n{}", limit.max(1));
    let format = entry_format();
    let mut args = vec!["log", &n, &format, "--"];
    args.extend(MANAGED);
    Ok(parse_entries(&git(dir, &args).await?))
}

/// One change of the history, by short or full hash.
pub async fn entry(dir: &Path, commit: &str) -> Result<HistoryEntry, String> {
    let (hash, _) = resolve(dir, commit).await?;
    let format = entry_format();
    let out = git(dir, &["log", "-1", &format, &hash]).await?;
    parse_entries(&out)
        .into_iter()
        .next()
        .ok_or_else(|| format!("cannot read change {commit}"))
}

fn parse_entries(out: &str) -> Vec<HistoryEntry> {
    out.split('\x1e')
        .filter_map(|entry| {
            let mut parts = entry.trim_start_matches('\n').splitn(5, '\x1f');
            Some(HistoryEntry {
                commit: parts.next()?.to_string(),
                time: parts.next()?.parse().ok()?,
                summary: parts.next()?.to_string(),
                recorded_action: parts.next().unwrap_or_default().trim().to_string(),
                by: parts.next().unwrap_or_default().trim().to_string(),
            })
        })
        .collect()
}

/// A change in tulsid's history, by short or full hash: (full hash, summary).
async fn resolve(dir: &Path, commit: &str) -> Result<(String, String), String> {
    let commit = commit.trim();
    if commit.len() < 4 || commit.len() > 64 || !commit.chars().all(|c| c.is_ascii_hexdigit()) {
        return Err(format!("{commit:?} is not a change id"));
    }
    let hash = git(
        dir,
        &[
            "rev-parse",
            "--verify",
            "-q",
            &format!("{commit}^{{commit}}"),
        ],
    )
    .await
    .map_err(|_| format!("there is no change {commit}"))?
    .trim()
    .to_string();
    let mut args = vec!["log", "--format=%H", "--"];
    args.extend(MANAGED);
    if !git(dir, &args).await?.lines().any(|l| l.trim() == hash) {
        return Err(format!("{commit} is not a change TulsiOS made"));
    }
    let summary = git(dir, &["log", "-1", "--format=%s", &hash])
        .await?
        .trim()
        .to_string();
    if git(dir, &["rev-parse", "--verify", "-q", &format!("{hash}^")])
        .await
        .is_err()
    {
        return Err(format!(
            "\"{summary}\" is where the history starts; it cannot be undone"
        ));
    }
    Ok((hash, summary))
}

async fn show(dir: &Path, rev: &str, rel: &str) -> Option<Vec<u8>> {
    git(dir, &["show", &format!("{rev}:{rel}")])
        .await
        .ok()
        .map(String::into_bytes)
}

/// What undoing change `commit` (any change, not only the latest) means for each
/// managed file it touched, applied on top of everything since. Returns the file
/// changes and that change's summary.
/// - state.json is reverted by meaning (`State::reverted`), so it never conflicts.
/// - Other files (configuration.nix, local packages) are merged three-way: if a later
///   change edited the same lines, nothing is changed and the error says so.
pub async fn revert_changes(dir: &Path, commit: &str) -> Result<(Vec<FileChange>, String), String> {
    let (hash, summary) = resolve(dir, commit).await?;
    let parent = format!("{hash}^");
    let mut args = vec!["show", "--name-only", "--format=", &hash, "--"];
    args.extend(MANAGED);
    let touched = git(dir, &args).await?;
    let mut changes = Vec::new();
    for rel in touched.lines().map(str::trim).filter(|l| is_managed(l)) {
        let current = read(dir, rel);
        let at = show(dir, &hash, rel).await;
        let before = show(dir, &parent, rel).await;
        if rel == Config::LOCK_REL && before.is_none() {
            // The change that first wrote flake.lock (a development flake's first
            // rebuild). Without a lock the next rebuild would fetch the newest
            // inputs: an upgrade nobody asked for. Keep it.
            continue;
        }
        let new = if rel == Config::STATE_REL {
            let parse = |bytes: Option<Vec<u8>>| -> Result<State, String> {
                let text = String::from_utf8_lossy(bytes.as_deref().unwrap_or(b"{\"version\":1}"))
                    .into_owned();
                State::from_json(&text).map_err(|e| format!("cannot read {rel}: {e}"))
            };
            let reverted = parse(current.clone())?.reverted(&parse(before)?, &parse(at)?);
            Some(reverted.to_json_pretty().into_bytes())
        } else if current == at {
            before
        } else {
            match (&current, &at, &before) {
                (Some(cur), Some(base), Some(other)) => Some(
                    merge(dir, cur, base, other)
                        .await
                        .map_err(|_| conflict(&summary, rel))?,
                ),
                _ => return Err(conflict(&summary, rel)),
            }
        };
        if new != current {
            changes.push(FileChange {
                rel: rel.to_string(),
                old: current,
                new,
            });
        }
    }
    if changes.is_empty() {
        return Err(format!(
            "nothing left to undo in \"{summary}\": later changes already took it back"
        ));
    }
    Ok((changes, summary))
}

fn conflict(summary: &str, rel: &str) -> String {
    format!(
        "cannot undo \"{summary}\" on its own: a later change edited the same part of {rel}; \
         undo that later change first"
    )
}

/// Three-way merge: the change from `base` to `other`, applied to `current`.
async fn merge(dir: &Path, current: &[u8], base: &[u8], other: &[u8]) -> Result<Vec<u8>, String> {
    static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let n = NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let tmp = std::env::temp_dir().join(format!("tulsid-merge-{}-{n}", std::process::id()));
    std::fs::create_dir_all(&tmp).map_err(|e| e.to_string())?;
    let paths = [tmp.join("current"), tmp.join("base"), tmp.join("other")];
    let result = async {
        for (path, bytes) in paths.iter().zip([current, base, other]) {
            std::fs::write(path, bytes).map_err(|e| e.to_string())?;
        }
        let p: Vec<String> = paths.iter().map(|p| p.display().to_string()).collect();
        git(dir, &["merge-file", "-p", &p[0], &p[1], &p[2]]).await
    }
    .await;
    let _ = std::fs::remove_dir_all(&tmp);
    result.map(String::into_bytes)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn history_reads_back_the_recorded_action() {
        let dir = std::env::temp_dir().join(format!("tulsid-git-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        git(&dir, &["init", "-q"]).await.unwrap();
        for (summary, action) in [
            ("tulsi: install vlc", tulsi_client::ACTION_APPLY),
            (
                "tulsi: edit configuration.nix: add bob",
                tulsi_client::ACTION_CONFIGURE,
            ),
        ] {
            put(&dir, Config::CONFIG_REL, Some(summary.as_bytes()))
                .await
                .unwrap();
            commit(
                &dir,
                &commit_message(summary, action, "starah-assistant"),
                &[Config::CONFIG_REL],
            )
            .await
            .unwrap();
        }
        // A change recorded before ADR 0014 has no trailer.
        put(&dir, Config::CONFIG_REL, Some(b"old")).await.unwrap();
        commit(&dir, "tulsi: install hello", &[Config::CONFIG_REL])
            .await
            .unwrap();

        let entries = history(&dir, 10).await.unwrap();
        let got: Vec<(&str, &str)> = entries
            .iter()
            .map(|e| (e.summary.as_str(), e.action()))
            .collect();
        assert_eq!(
            got,
            [
                ("tulsi: install hello", tulsi_client::ACTION_APPLY),
                (
                    "tulsi: edit configuration.nix: add bob",
                    tulsi_client::ACTION_CONFIGURE
                ),
                ("tulsi: install vlc", tulsi_client::ACTION_APPLY),
            ]
        );
        assert!(entries[0].recorded_action.is_empty());
        assert!(entries[0].by.is_empty());
        assert_eq!(entries[1].by, "starah-assistant");
        assert_eq!(
            entry(&dir, &entries[1].commit).await.unwrap().by,
            "starah-assistant"
        );
        let _ = std::fs::remove_dir_all(&dir);
    }

    async fn repo(name: &str) -> std::path::PathBuf {
        let dir = std::env::temp_dir().join(format!("tulsid-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        git(&dir, &["init", "-q"]).await.unwrap();
        dir
    }

    /// Writes `files` and commits them; returns the short hash.
    async fn change(dir: &Path, files: &[(&str, String)], summary: &str) -> String {
        for (rel, text) in files {
            put(dir, rel, Some(text.as_bytes())).await.unwrap();
        }
        let rels: Vec<&str> = files.iter().map(|(r, _)| *r).collect();
        commit(
            dir,
            &commit_message(summary, tulsi_client::ACTION_APPLY, "alice"),
            &rels,
        )
        .await
        .unwrap()
    }

    #[tokio::test]
    async fn an_older_change_is_undone_and_later_ones_stay() {
        let dir = repo("revert-state").await;
        let state = |pkgs: &[&str]| {
            State {
                packages: pkgs.iter().map(|p| p.to_string()).collect(),
                ..State::default()
            }
            .to_json_pretty()
        };
        change(
            &dir,
            &[(Config::STATE_REL, state(&[]))],
            "tulsi: track state",
        )
        .await;
        let cowsay = change(
            &dir,
            &[(Config::STATE_REL, state(&["cowsay"]))],
            "tulsi: install cowsay",
        )
        .await;
        change(
            &dir,
            &[(Config::STATE_REL, state(&["cowsay", "hello"]))],
            "tulsi: install hello",
        )
        .await;

        let (changes, summary) = revert_changes(&dir, &cowsay).await.unwrap();
        assert_eq!(summary, "tulsi: install cowsay");
        assert_eq!(changes.len(), 1);
        let new =
            State::from_json(&String::from_utf8(changes[0].new.clone().unwrap()).unwrap()).unwrap();
        assert_eq!(new.packages, vec!["hello"]);

        assert!(revert_changes(&dir, "--help").await.is_err());
        assert!(revert_changes(&dir, "deadbeef").await.is_err());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[tokio::test]
    async fn configuration_edits_merge_or_refuse() {
        let dir = repo("revert-config").await;
        let lines = |l: &[&str]| l.iter().map(|x| format!("{x}\n")).collect::<String>();
        let cfg = Config::CONFIG_REL;
        change(
            &dir,
            &[(cfg, lines(&["a", "1", "2", "3", "4", "c"]))],
            "tulsi: start",
        )
        .await;
        let first = change(
            &dir,
            &[(cfg, lines(&["A", "1", "2", "3", "4", "c"]))],
            "tulsi: edit a",
        )
        .await;
        change(
            &dir,
            &[(cfg, lines(&["A", "1", "2", "3", "4", "C"]))],
            "tulsi: edit c",
        )
        .await;

        // A later edit elsewhere in the file: the older edit is taken back on its own.
        let (changes, _) = revert_changes(&dir, &first).await.unwrap();
        assert_eq!(
            changes[0].new.as_deref(),
            Some(lines(&["a", "1", "2", "3", "4", "C"]).as_bytes())
        );

        // A later edit of the same line: refused.
        change(
            &dir,
            &[(cfg, lines(&["AA", "1", "2", "3", "4", "C"]))],
            "tulsi: edit a again",
        )
        .await;
        let err = revert_changes(&dir, &first).await.unwrap_err();
        assert!(err.contains("a later change edited the same part"), "{err}");
        let _ = std::fs::remove_dir_all(&dir);
    }
}
