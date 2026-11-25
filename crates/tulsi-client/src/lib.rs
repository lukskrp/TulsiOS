//! Client side of the tulsid D-Bus API, `org.tulsi.Manager1`.
//!
//! Used by the `tulsi` CLI and, later, the Software Center, the Assistant
//! (via tulsi-mcp) and the browser bridge.
//!
//! ## API
//! | Member | Kind | Notes |
//! |---|---|---|
//! | `GetState() -> s` | method | state.json contents |
//! | `Plan(ops: s) -> s` | method | JSON [`Plan`]: changes + resulting state, nothing applied |
//! | `Apply(ops: s) -> t` | method | polkit `org.tulsi.apply`; returns job id, 0 = nothing to do |
//! | `Undo() -> t` | method | `UndoChange` of the latest change |
//! | `UndoChange(commit: s) -> t` | method | takes back any earlier change, keeping later ones; polkit: the action that change needed ([`HistoryEntry::action`]); error `Invalid` if a later change edited the same lines |
//! | `PlanUndo(commit: s) -> s` | method | JSON [`UndoPlan`]: what `UndoChange` would change; nothing applied |
//! | `History(limit: u) -> s` | method | JSON list of [`HistoryEntry`] |
//! | `Search(query: s, limit: u) -> s` | method | JSON list of [`PackageInfo`], best first |
//! | `PackageInfo(attr: s) -> s` | method | JSON [`PackageInfo`]; error `NotFound` |
//! | `GetConfig() -> s` | method | configuration.nix ("" if absent) |
//! | `PlanConfig(contents: s) -> s` | method | syntax check + JSON [`ConfigPlan`]; nothing written |
//! | `ApplyConfig(contents: s, summary: s) -> t` | method | polkit `org.tulsi.apply` if a rollback fully undoes the edit, else `org.tulsi.configure` ([`config_action`]); job id, 0 = unchanged |
//! | `CheckUpgrade() -> s` | method | JSON [`UpgradeInfo`]: is there a newer TulsiOS release on the branch this machine follows (needs the network; problems are in `error`) |
//! | `Upgrade() -> t` | method | polkit `org.tulsi.upgrade`; moves flake.lock's `tulsi` to the newest release and rebuilds; job id; undone like any change (ADR 0017) |
//! | `Busy` | property | a job is running |
//! | `Progress(job: t, line: s)` | signal | rebuild output |
//! | `Finished(job: t, success: b, message: s)` | signal | job result |
//!
//! `ops` is a JSON array of [`tulsi_state::Op`].

use serde::{Deserialize, Serialize};

pub mod agents;

pub use tulsi_state::{Browser, Op, State};

pub const BUS_NAME: &str = "org.tulsi.Manager1";
pub const OBJECT_PATH: &str = "/org/tulsi/Manager1";
pub const ACTION_APPLY: &str = "org.tulsi.apply";
/// Used instead of ACTION_APPLY when a change only adds/removes browser
/// extensions, so it can be allowed more freely (see tulsi.browserExtensions).
pub const ACTION_EXTENSIONS: &str = "org.tulsi.extensions";
/// configuration.nix edits a NixOS rollback does not fully undo (accounts, boot, file
/// systems, scripts, …; ADR 0014). Starah asks the human about these at level 2.
pub const ACTION_CONFIGURE: &str = "org.tulsi.configure";
/// Moving to a newer TulsiOS release (ADR 0017). Reversible (undo restores the
/// previous release), but it changes the whole system, so it has its own action.
pub const ACTION_UPGRADE: &str = "org.tulsi.upgrade";

/// Whether a newer TulsiOS release is available (`CheckUpgrade`).
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct UpgradeInfo {
    /// The release branch this machine follows, e.g. `github:lukskrp/TulsiOS/stable`;
    /// empty for a local source (development flakes), which cannot upgrade.
    pub following: String,
    pub current_rev: String,
    /// The VERSION of the release in use ("unknown" if it cannot be read).
    pub current_version: String,
    /// The branch's newest commit and its VERSION (empty if it could not be fetched).
    pub available_rev: String,
    pub available_version: String,
    /// The branch has moved past the release in use.
    pub available: bool,
    /// Why nothing could be checked (no network, a local source, …); empty if fine.
    pub error: String,
}

/// The polkit action for applying `ops`. Browser extensions alone have their own
/// action. Adding a local package (code an agent may have written, which ends up on
/// the user's `PATH`) is [`ACTION_CONFIGURE`]. Everything else a rollback fully
/// undoes, so it is [`ACTION_APPLY`].
pub fn ops_action(ops: &[Op]) -> &'static str {
    if ops
        .iter()
        .any(|op| matches!(op, Op::AddLocalPackage { .. }))
    {
        ACTION_CONFIGURE
    } else if ops
        .iter()
        .all(|op| matches!(op, Op::AddExtension { .. } | Op::RemoveExtension { .. }))
    {
        ACTION_EXTENSIONS
    } else {
        ACTION_APPLY
    }
}

/// The polkit action for replacing configuration.nix `old` with `new`, and the
/// settings that make it [`ACTION_CONFIGURE`] (empty for [`ACTION_APPLY`]).
pub fn config_action(old: &str, new: &str) -> (&'static str, Vec<String>) {
    let outside = tulsi_state::unreversible_settings(old, new);
    if outside.is_empty() {
        (ACTION_APPLY, outside)
    } else {
        (ACTION_CONFIGURE, outside)
    }
}

/// Commit trailer recording the polkit action a change needed; undoing it needs
/// the same one.
pub const ACTION_TRAILER: &str = "Tulsi-Action";
/// Commit trailer naming the account that asked for a change (`starah-<agent>` for
/// an AI agent).
pub const BY_TRAILER: &str = "Tulsi-By";

/// What undoing one change would do.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UndoPlan {
    pub commit: String,
    pub summary: String,
    /// state.json differences ("+ package vlc", …) and other files touched.
    pub changes: Vec<String>,
    /// The polkit action undoing it needs.
    pub action: String,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ops(json: &str) -> Vec<Op> {
        serde_json::from_str(json).unwrap()
    }

    #[test]
    fn ops_action_follows_reversibility() {
        assert_eq!(
            ops_action(&ops(r#"[{"op":"addPackage","name":"vlc"}]"#)),
            ACTION_APPLY
        );
        assert_eq!(
            ops_action(&ops(
                r#"[{"op":"setService","name":"printing","enable":true}]"#
            )),
            ACTION_APPLY
        );
        assert_eq!(
            ops_action(&ops(
                r#"[{"op":"addExtension","browser":"firefox","id":"uBlock0@raymondhill.net"}]"#
            )),
            ACTION_EXTENSIONS
        );
        assert_eq!(
            ops_action(&ops(
                r#"[{"op":"addLocalPackage","name":"frob","expression":"{ stdenv }: stdenv.mkDerivation { }"}]"#
            )),
            ACTION_CONFIGURE
        );
        assert_eq!(
            ops_action(&ops(r#"[{"op":"removeLocalPackage","name":"frob"}]"#)),
            ACTION_APPLY
        );
    }

    #[test]
    fn old_history_entries_get_an_action() {
        let entry = |summary: &str| HistoryEntry {
            commit: "x".into(),
            time: 0,
            summary: summary.into(),
            recorded_action: String::new(),
            by: String::new(),
        };
        assert_eq!(entry("tulsi: install vlc").action(), ACTION_APPLY);
        assert_eq!(
            entry("tulsi: edit configuration.nix: x").action(),
            ACTION_CONFIGURE
        );
        assert_eq!(
            entry("tulsi: undo edit configuration.nix: x").action(),
            ACTION_CONFIGURE
        );
        let mut recorded = entry("tulsi: install vlc");
        recorded.recorded_action = ACTION_EXTENSIONS.into();
        assert_eq!(recorded.action(), ACTION_EXTENSIONS);
    }
}

/// Set `TULSI_BUS=session` to talk to a tulsid running on the session bus
/// (development without a NixOS machine).
pub const BUS_ENV: &str = "TULSI_BUS";

#[zbus::proxy(
    interface = "org.tulsi.Manager1",
    default_service = "org.tulsi.Manager1",
    default_path = "/org/tulsi/Manager1"
)]
pub trait Manager {
    fn get_state(&self) -> zbus::Result<String>;
    fn plan(&self, ops: &str) -> zbus::Result<String>;
    fn apply(&self, ops: &str) -> zbus::Result<u64>;
    fn undo(&self) -> zbus::Result<u64>;
    fn undo_change(&self, commit: &str) -> zbus::Result<u64>;
    fn plan_undo(&self, commit: &str) -> zbus::Result<String>;
    fn history(&self, limit: u32) -> zbus::Result<String>;
    fn search(&self, query: &str, limit: u32) -> zbus::Result<String>;
    /// `hint` is a [`MatchHint`] as JSON; returns [`Candidate`]s as JSON.
    #[zbus(name = "Match")]
    fn match_(&self, hint: &str, limit: u32) -> zbus::Result<String>;
    fn package_info(&self, attr: &str) -> zbus::Result<String>;
    fn get_config(&self) -> zbus::Result<String>;
    fn plan_config(&self, contents: &str) -> zbus::Result<String>;
    fn apply_config(&self, contents: &str, summary: &str) -> zbus::Result<u64>;
    fn check_upgrade(&self) -> zbus::Result<String>;
    fn upgrade(&self) -> zbus::Result<u64>;

    #[zbus(property)]
    fn busy(&self) -> zbus::Result<bool>;

    #[zbus(signal)]
    fn progress(&self, job: u64, line: String) -> zbus::Result<()>;

    #[zbus(signal)]
    fn finished(&self, job: u64, success: bool, message: String) -> zbus::Result<()>;
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub changes: Vec<String>,
    pub state: State,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HistoryEntry {
    pub commit: String,
    /// Unix timestamp (seconds).
    pub time: i64,
    pub summary: String,
    /// The polkit action the change needed (its `Tulsi-Action` trailer); empty for
    /// changes recorded before ADR 0014. Use [`HistoryEntry::action`].
    #[serde(default, skip_serializing_if = "String::is_empty", rename = "action")]
    pub recorded_action: String,
    /// Who asked for the change (its `Tulsi-By` trailer): a user name, or
    /// `starah-<agent>` for an AI agent; empty if not recorded.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub by: String,
}

impl HistoryEntry {
    /// The polkit action this change needed, which undoing it needs too. Older
    /// changes without a record: configuration edits count as `org.tulsi.configure`.
    pub fn action(&self) -> &str {
        if !self.recorded_action.is_empty() {
            return &self.recorded_action;
        }
        let summary = self.summary.trim_start_matches("tulsi: ");
        let summary = summary.strip_prefix("undo ").unwrap_or(summary);
        if summary.starts_with("edit configuration.nix") {
            ACTION_CONFIGURE
        } else {
            ACTION_APPLY
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConfigPlan {
    pub changed: bool,
    /// Unified diff against the current configuration.nix.
    pub diff: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PackageInfo {
    /// nixpkgs attribute path, what goes into state.json.
    pub attr: String,
    pub pname: String,
    pub version: String,
    pub description: String,
    /// Needs `nixpkgs.config.allowUnfree`.
    pub unfree: bool,
    /// Listed in state.json.
    pub installed: bool,
    /// For unfree packages on tulsid's allow-list: the licence a person must accept
    /// before installing (`acceptLicense` op). None for everything else.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub license: Option<License>,
    /// The licence is already accepted (state.json `acceptedLicenses`).
    #[serde(default)]
    pub license_accepted: bool,
    /// Made on this machine (state.json `localPackages`), with where it came from.
    #[serde(default)]
    pub local: bool,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub origin: String,
}

/// What someone tried to install, for `Match` (ADR 0018): the names it goes by
/// (typed, or a package's own name), the programs it contains or that were typed,
/// what it says it provides, and the tool it was asked of (`apt`, `pip`, `flatpak`…).
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct MatchHint {
    pub names: Vec<String>,
    pub programs: Vec<String>,
    pub provides: Vec<String>,
    pub tool: String,
}

/// One answer of `Match`: a package to install or a service to turn on, and why.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "camelCase")]
pub enum Candidate {
    Package {
        #[serde(flatten)]
        info: PackageInfo,
        /// Why it matches, for people: "provides the program `rg`".
        reason: String,
    },
    Service {
        /// `services.<name>.enable`.
        name: String,
        /// Already on in state.json.
        enabled: bool,
        reason: String,
    },
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct License {
    pub name: String,
    #[serde(default)]
    pub url: String,
}

/// Desktop notifications (org.freedesktop.Notifications, on the session bus), for
/// tulsi-extwatch and `tulsi upgrade --notify`.
#[zbus::proxy(
    interface = "org.freedesktop.Notifications",
    default_service = "org.freedesktop.Notifications",
    default_path = "/org/freedesktop/Notifications"
)]
pub trait Notifications {
    #[allow(clippy::too_many_arguments)]
    fn notify(
        &self,
        app_name: &str,
        replaces_id: u32,
        app_icon: &str,
        summary: &str,
        body: &str,
        actions: &[&str],
        hints: std::collections::HashMap<&str, zbus::zvariant::Value<'_>>,
        expire_timeout: i32,
    ) -> zbus::Result<u32>;

    #[zbus(signal)]
    fn action_invoked(&self, id: u32, action_key: String) -> zbus::Result<()>;
}

/// Connects to the system bus, or the session bus if `TULSI_BUS=session`.
pub async fn connect() -> zbus::Result<zbus::Connection> {
    if std::env::var(BUS_ENV).as_deref() == Ok("session") {
        zbus::Connection::session().await
    } else {
        zbus::Connection::system().await
    }
}
