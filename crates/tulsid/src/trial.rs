//! Changes that take effect at the next restart, on trial (ADR 0029).
//!
//! A driver change can leave a black screen, where nobody can click Undo. So it
//! is built for the next start (`nixos-rebuild boot`) and put on trial:
//!
//! - **systemd-boot:** the system before stays the default boot entry and the new
//!   one is chosen for the next start only (`bootctl set-oneshot`). If that start
//!   goes wrong, any restart brings back the system before.
//! - **GRUB** has no one-shot entry: the new system is the default, and if nobody
//!   keeps it within [`Config::trial_timeout_secs`] of starting, the change is
//!   undone, so the restart after brings back the system before.
//!
//! The person keeps it (`KeepTrial`) once they see it works. When tulsid starts
//! in a boot that isn't the new system (the person went back), the change is
//! undone and a notice is left for them.

use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use tokio::process::Command;

use crate::config::Config;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum State {
    /// Built for the next start, which hasn't happened yet.
    Pending,
    /// Started with the new system; waiting for the person to keep it.
    Testing,
    /// Undone without the person asking (they went back, or didn't keep it in
    /// time); the notice says why. Cleared by `DismissTrial`.
    Reverted,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Trial {
    pub state: State,
    /// The commit that made the change.
    pub commit: String,
    pub summary: String,
    pub old_generation: Option<u64>,
    pub new_generation: Option<u64>,
    /// The new system's store path, to compare with /run/booted-system.
    pub new_system: Option<String>,
    pub boot_loader: String,
    /// The boot the trial was last looked at in (`/proc/sys/kernel/random/boot_id`).
    pub boot_id: String,
    /// Unix time it was made.
    pub at: u64,
    /// Unix time the new system started (GRUB's time limit counts from it).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tested_at: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub notice: Option<String>,
}

pub fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

/// "10 minutes", or "20 seconds" for short limits (tests).
pub fn duration(secs: u64) -> String {
    if secs < 120 {
        format!("{secs} seconds")
    } else {
        format!("{} minutes", secs / 60)
    }
}

pub fn boot_id() -> String {
    std::fs::read_to_string("/proc/sys/kernel/random/boot_id")
        .map(|s| s.trim().to_string())
        .unwrap_or_default()
}

pub fn load(cfg: &Config) -> Option<Trial> {
    let text = std::fs::read_to_string(&cfg.trial_file).ok()?;
    serde_json::from_str(&text).ok()
}

pub fn save(cfg: &Config, trial: &Trial) -> Result<(), String> {
    if let Some(dir) = cfg.trial_file.parent() {
        std::fs::create_dir_all(dir).map_err(|e| format!("{}: {e}", dir.display()))?;
    }
    let text = serde_json::to_string_pretty(trial).expect("trial serializes");
    crate::git::write_atomic(&cfg.trial_file, text.as_bytes())
}

pub fn remove(cfg: &Config) {
    let _ = std::fs::remove_file(&cfg.trial_file);
}

/// The status as JSON for `TrialStatus`: the trial, or `{"state": "none"}`.
pub fn status_json(cfg: &Config) -> String {
    match load(cfg) {
        Some(t) => serde_json::to_string(&t).expect("trial serializes"),
        None => r#"{"state":"none"}"#.to_string(),
    }
}

/// The generation number a profile link points at (`system-42-link` → 42).
pub fn generation(profile: &Path) -> Option<u64> {
    let target = std::fs::read_link(profile).ok()?;
    let name = target.file_name()?.to_str()?;
    let prefix = format!("{}-", profile.file_name()?.to_str()?);
    name.strip_prefix(&prefix)?
        .strip_suffix("-link")?
        .parse()
        .ok()
}

/// The store path of generation `n` of `profile`.
pub fn generation_system(profile: &Path, n: u64) -> Option<String> {
    let link = profile.with_file_name(format!("{}-{n}-link", profile.file_name()?.to_str()?));
    std::fs::canonicalize(link)
        .ok()
        .map(|p| p.display().to_string())
}

pub fn booted_system(cfg: &Config) -> Option<String> {
    std::fs::canonicalize(&cfg.booted_system)
        .ok()
        .map(|p| p.display().to_string())
}

/// The rebuild command that only prepares the next start: `switch` becomes `boot`.
pub fn boot_command(cfg: &Config) -> Vec<String> {
    if !cfg.boot_rebuild_command.is_empty() {
        return cfg.boot_rebuild_command.clone();
    }
    cfg.rebuild_command
        .iter()
        .map(|a| {
            if a == "switch" {
                "boot".to_string()
            } else {
                a.clone()
            }
        })
        .collect()
}

/// The boot entry that starts `system`, from `bootctl list --json=short`.
/// (NixOS names entries by a hash of their contents, not by generation.)
pub fn entry_for(list: &str, system: &str) -> Option<String> {
    let entries: Vec<serde_json::Value> = serde_json::from_str(list).ok()?;
    let init = format!("init={system}/init");
    entries
        .iter()
        .find(|e| {
            e["options"]
                .as_str()
                .is_some_and(|o| o.split_whitespace().any(|w| w == init))
        })
        .and_then(|e| e["id"].as_str().map(str::to_string))
}

async fn entry(profile: &Path, n: u64) -> Result<String, String> {
    let system =
        generation_system(profile, n).ok_or_else(|| format!("system generation {n} is gone"))?;
    let list = bootctl(&["list", "--json=short", "--no-pager"]).await?;
    entry_for(&list, &system).ok_or_else(|| format!("no boot entry starts generation {n}"))
}

async fn bootctl(args: &[&str]) -> Result<String, String> {
    let out = Command::new("bootctl")
        .args(args)
        .output()
        .await
        .map_err(|e| format!("bootctl: {e}"))?;
    if out.status.success() {
        Ok(String::from_utf8_lossy(&out.stdout).into_owned())
    } else {
        Err(format!(
            "bootctl {}: {}",
            args.join(" "),
            String::from_utf8_lossy(&out.stderr).trim()
        ))
    }
}

/// Makes the next start (only) use the new system.
pub async fn arm(cfg: &Config, old: u64, new: u64) -> Result<(), String> {
    if cfg.boot_loader == "systemd-boot" {
        let old = entry(&cfg.system_profile, old).await?;
        let new = entry(&cfg.system_profile, new).await?;
        bootctl(&["set-default", &old]).await?;
        bootctl(&["set-oneshot", &new]).await?;
    }
    Ok(())
}

/// Back to the boot loader's own choice: the newest system.
pub async fn disarm(cfg: &Config) -> Result<(), String> {
    if cfg.boot_loader == "systemd-boot" {
        bootctl(&["set-oneshot", ""]).await?;
        bootctl(&["set-default", ""]).await?;
        // (Both remove their EFI variable: loader.conf's default, the newest, wins.)
    }
    Ok(())
}

/// What to do with a trial when tulsid starts.
#[derive(Debug, PartialEq, Eq)]
pub enum Check {
    /// Nothing (no trial, the same boot, or already undone).
    Nothing,
    /// Started with the new system: it is now on test.
    Testing,
    /// Started with something else: undo the change.
    Revert,
}

pub fn check(trial: &Trial, booted: Option<&str>, this_boot: &str) -> Check {
    match trial.state {
        State::Reverted => Check::Nothing,
        _ if trial.boot_id == this_boot => Check::Nothing,
        _ if booted.is_some() && booted == trial.new_system.as_deref() => Check::Testing,
        _ => Check::Revert,
    }
}

pub fn default_trial_file() -> PathBuf {
    PathBuf::from("/var/lib/tulsi/trial.json")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn trial(state: State) -> Trial {
        Trial {
            state,
            commit: "abc".into(),
            summary: "Drivers".into(),
            old_generation: Some(4),
            new_generation: Some(5),
            new_system: Some("/nix/store/new".into()),
            boot_loader: "systemd-boot".into(),
            boot_id: "boot-1".into(),
            at: 0,
            tested_at: None,
            notice: None,
        }
    }

    #[test]
    fn same_boot_does_nothing() {
        assert_eq!(
            check(&trial(State::Pending), Some("/nix/store/old"), "boot-1"),
            Check::Nothing
        );
    }

    #[test]
    fn started_with_the_new_system_tests_it() {
        assert_eq!(
            check(&trial(State::Pending), Some("/nix/store/new"), "boot-2"),
            Check::Testing
        );
        // GRUB: a restart without keeping it lands on it again.
        assert_eq!(
            check(&trial(State::Testing), Some("/nix/store/new"), "boot-3"),
            Check::Testing
        );
    }

    #[test]
    fn started_with_anything_else_reverts() {
        assert_eq!(
            check(&trial(State::Pending), Some("/nix/store/old"), "boot-2"),
            Check::Revert
        );
        assert_eq!(
            check(&trial(State::Testing), Some("/nix/store/old"), "boot-3"),
            Check::Revert
        );
        assert_eq!(check(&trial(State::Testing), None, "boot-3"), Check::Revert);
    }

    #[test]
    fn reverted_stays_until_dismissed() {
        assert_eq!(
            check(&trial(State::Reverted), Some("/nix/store/old"), "boot-2"),
            Check::Nothing
        );
    }

    #[test]
    fn generation_numbers_from_profile_links() {
        let dir = std::env::temp_dir().join(format!("tulsid-trial-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let profile = dir.join("system");
        let _ = std::fs::remove_file(&profile);
        std::os::unix::fs::symlink("system-42-link", &profile).unwrap();
        assert_eq!(generation(&profile), Some(42));
        std::fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn boot_entry_by_its_system() {
        let list = r#"[
            {"id": "nixos-aaa.conf", "options": "init=/nix/store/new-system/init console=ttyS0"},
            {"id": "nixos-bbb.conf", "options": "init=/nix/store/old-system/init console=ttyS0"},
            {"id": "auto-reboot-to-firmware-setup"}
        ]"#;
        assert_eq!(
            entry_for(list, "/nix/store/old-system").as_deref(),
            Some("nixos-bbb.conf")
        );
        assert_eq!(entry_for(list, "/nix/store/old"), None);
    }

    #[test]
    fn boot_command_replaces_switch() {
        let cfg: Config = serde_json::from_str(
            r#"{"flakeDir": "/etc/nixos", "rebuildCommand": ["nixos-rebuild", "switch", "--flake", "/etc/nixos#h"]}"#,
        )
        .unwrap();
        assert_eq!(
            boot_command(&cfg),
            ["nixos-rebuild", "boot", "--flake", "/etc/nixos#h"]
        );
    }
}
