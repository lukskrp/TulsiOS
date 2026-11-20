//! Upgrading to a newer TulsiOS release (ADR 0017).
//!
//! An installed machine's system flake has `inputs.tulsi.url` = the release branch
//! (`github:lukskrp/TulsiOS/stable`), and its flake.lock pins the release in use.
//! Upgrading moves that pin to the branch's newest commit, through the ordinary
//! transaction: write flake.lock, rebuild, commit; restore it if the rebuild fails.
//! Undoing the upgrade puts the old pin back, whose sources are still in the store.

use std::path::{Path, PathBuf};

use serde_json::Value;
use tokio::process::Command;
use tulsi_client::UpgradeInfo;

use crate::config::Config;

/// The `tulsi` input's node in a flake.lock.
fn tulsi_node(lock: &Value) -> Option<&Value> {
    let root = lock["root"].as_str()?;
    let name = lock["nodes"][root]["inputs"]["tulsi"].as_str()?;
    lock["nodes"].get(name)
}

/// The flake reference the `tulsi` input follows, or None for a local source
/// (path:, a development flake), which has no newer release to fetch.
pub fn followed_url(lock: &Value) -> Option<String> {
    let original = &tulsi_node(lock)?["original"];
    let branch = original["ref"].as_str();
    match original["type"].as_str()? {
        "github" => {
            let base = format!(
                "github:{}/{}",
                original["owner"].as_str()?,
                original["repo"].as_str()?
            );
            Some(match branch {
                Some(r) => format!("{base}/{r}"),
                None => base,
            })
        }
        "git" => {
            let base = format!("git+{}", original["url"].as_str()?);
            Some(match branch {
                Some(r) => format!("{base}?ref={r}"),
                None => base,
            })
        }
        _ => None,
    }
}

/// The git revision the `tulsi` input is pinned to.
pub fn locked_rev(lock: &Value) -> Option<String> {
    tulsi_node(lock)?["locked"]["rev"]
        .as_str()
        .map(str::to_string)
}

fn nix() -> Command {
    let mut cmd = Command::new("nix");
    cmd.args(["--extra-experimental-features", "nix-command flakes"]);
    // Only direct references (github:, git+file:) are used here; without this,
    // `flake prefetch` downloads the global flake registry first, which fails offline.
    cmd.args(["--option", "flake-registry", ""]);
    cmd
}

async fn nix_json(args: &[&str]) -> Result<Value, String> {
    let out = nix()
        .args(args)
        .output()
        .await
        .map_err(|e| format!("cannot run nix: {e}"))?;
    if !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr);
        let last = err
            .lines()
            .rev()
            .find(|l| !l.trim().is_empty())
            .unwrap_or("nix failed");
        return Err(last.trim().to_string());
    }
    serde_json::from_slice(&out.stdout).map_err(|e| format!("cannot read nix's output: {e}"))
}

/// The newest commit on `url` and its source in the store (downloaded if needed).
/// `prefetch`, not `metadata`: with lazy trees, metadata names a store path that
/// need not exist yet.
async fn latest(url: &str) -> Result<(String, PathBuf), String> {
    let fetched = nix_json(&["flake", "prefetch", "--json", "--refresh", url]).await?;
    let rev = fetched["locked"]["rev"]
        .as_str()
        .ok_or("the release branch has no revision")?
        .to_string();
    let path = fetched["storePath"]
        .as_str()
        .ok_or("nix did not report a store path")?;
    Ok((rev, PathBuf::from(path)))
}

/// The TulsiOS version (the VERSION file) of a source tree.
fn version_at(source: &Path) -> String {
    match std::fs::read_to_string(source.join("VERSION")) {
        Ok(v) => v.trim().to_string(),
        Err(e) => {
            eprintln!(
                "tulsid: upgrade: cannot read {}/VERSION: {e}",
                source.display()
            );
            "unknown".into()
        }
    }
}

/// The source the `tulsi` input is pinned to now. `archive` (not `--dry-run`, which
/// with lazy trees may name a path not in the store yet) makes sure it is in the
/// store; offline, since a pinned source never needs downloading again.
async fn current_source(dir: &Path) -> Option<PathBuf> {
    let flake = format!("path:{}", dir.display());
    let archive = nix_json(&["flake", "archive", "--json", "--offline", &flake]).await;
    match archive {
        Ok(a) => {
            let path = a["inputs"]["tulsi"]["path"].as_str().map(PathBuf::from);
            if path.is_none() {
                eprintln!("tulsid: upgrade: no `tulsi` input in {a}");
            }
            path
        }
        Err(e) => {
            eprintln!("tulsid: upgrade: cannot find the TulsiOS source in use: {e}");
            None
        }
    }
}

/// What `CheckUpgrade` reports. Never fails: problems (no network, a local
/// source) are in `error`.
pub async fn check(dir: &Path) -> UpgradeInfo {
    let mut info = UpgradeInfo::default();
    let lock: Value = match std::fs::read(dir.join(Config::LOCK_REL))
        .map_err(|e| e.to_string())
        .and_then(|b| serde_json::from_slice(&b).map_err(|e| e.to_string()))
    {
        Ok(lock) => lock,
        Err(e) => {
            info.error = format!("cannot read flake.lock: {e}");
            return info;
        }
    };
    info.current_rev = locked_rev(&lock).unwrap_or_default();
    info.current_version = match current_source(dir).await {
        Some(src) => version_at(&src),
        None => "unknown".into(),
    };
    let Some(url) = followed_url(&lock) else {
        info.error = "this system uses a local TulsiOS source, not a release branch".into();
        return info;
    };
    info.following = url.clone();
    match latest(&url).await {
        Ok((rev, source)) => {
            info.available = rev != info.current_rev;
            info.available_version = version_at(&source);
            info.available_rev = rev;
        }
        Err(e) => info.error = format!("cannot reach {url}: {e}"),
    }
    info
}

/// flake.lock with the `tulsi` input moved to the newest commit of the branch it
/// follows (and TulsiOS's own pins with it). Computed in a scratch copy: the real
/// flake.lock only changes inside the transaction.
pub async fn updated_lock(dir: &Path) -> Result<Vec<u8>, String> {
    static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let n = NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let tmp = std::env::temp_dir().join(format!("tulsid-upgrade-{}-{n}", std::process::id()));
    let result = async {
        std::fs::create_dir_all(&tmp).map_err(|e| e.to_string())?;
        for rel in ["flake.nix", Config::LOCK_REL] {
            std::fs::copy(dir.join(rel), tmp.join(rel))
                .map_err(|e| format!("cannot copy {rel}: {e}"))?;
        }
        let flake = format!("path:{}", tmp.display());
        let out = nix()
            .args(["flake", "update", "tulsi", "--flake", &flake])
            .output()
            .await
            .map_err(|e| format!("cannot run nix: {e}"))?;
        if !out.status.success() {
            return Err(format!(
                "cannot update the TulsiOS release: {}",
                String::from_utf8_lossy(&out.stderr).trim()
            ));
        }
        std::fs::read(tmp.join(Config::LOCK_REL)).map_err(|e| e.to_string())
    }
    .await;
    let _ = std::fs::remove_dir_all(&tmp);
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lock(original: Value) -> Value {
        serde_json::json!({
            "nodes": {
                "root": { "inputs": { "tulsi": "tulsi" } },
                "tulsi": {
                    "locked": { "type": "github", "owner": "lukskrp", "repo": "TulsiOS", "rev": "a".repeat(40) },
                    "original": original
                }
            },
            "root": "root",
            "version": 7
        })
    }

    #[test]
    fn follows_the_release_branch() {
        let l = lock(serde_json::json!({
            "type": "github", "owner": "lukskrp", "repo": "TulsiOS", "ref": "stable"
        }));
        assert_eq!(
            followed_url(&l).as_deref(),
            Some("github:lukskrp/TulsiOS/stable")
        );
        assert_eq!(locked_rev(&l), Some("a".repeat(40)));
    }

    #[test]
    fn a_local_git_repo_works_too() {
        let l = lock(serde_json::json!({
            "type": "git", "url": "file:///srv/tulsios", "ref": "stable"
        }));
        assert_eq!(
            followed_url(&l).as_deref(),
            Some("git+file:///srv/tulsios?ref=stable")
        );
    }

    #[test]
    fn a_local_path_has_nothing_to_follow() {
        let l = lock(serde_json::json!({ "type": "path", "path": "/nix/store/x-source" }));
        assert_eq!(followed_url(&l), None);
    }
}
