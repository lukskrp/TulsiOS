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
//! | `Undo() -> t` | method | polkit `org.tulsi.apply`; reverts the latest change |
//! | `History(limit: u) -> s` | method | JSON list of [`HistoryEntry`] |
//! | `Search(query: s, limit: u) -> s` | method | JSON list of [`PackageInfo`], best first |
//! | `PackageInfo(attr: s) -> s` | method | JSON [`PackageInfo`]; error `NotFound` |
//! | `GetConfig() -> s` | method | configuration.nix ("" if absent) |
//! | `PlanConfig(contents: s) -> s` | method | syntax check + JSON [`ConfigPlan`]; nothing written |
//! | `ApplyConfig(contents: s, summary: s) -> t` | method | polkit `org.tulsi.apply`; job id, 0 = unchanged |
//! | `Busy` | property | a job is running |
//! | `Progress(job: t, line: s)` | signal | rebuild output |
//! | `Finished(job: t, success: b, message: s)` | signal | job result |
//!
//! `ops` is a JSON array of [`tulsi_state::Op`].

use serde::{Deserialize, Serialize};

pub use tulsi_state::{Browser, Op, State};

pub const BUS_NAME: &str = "org.tulsi.Manager1";
pub const OBJECT_PATH: &str = "/org/tulsi/Manager1";
pub const ACTION_APPLY: &str = "org.tulsi.apply";
/// Used instead of ACTION_APPLY when a change only adds/removes browser
/// extensions, so it can be allowed more freely (see tulsi.browserExtensions).
pub const ACTION_EXTENSIONS: &str = "org.tulsi.extensions";

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
    fn history(&self, limit: u32) -> zbus::Result<String>;
    fn search(&self, query: &str, limit: u32) -> zbus::Result<String>;
    fn package_info(&self, attr: &str) -> zbus::Result<String>;
    fn get_config(&self) -> zbus::Result<String>;
    fn plan_config(&self, contents: &str) -> zbus::Result<String>;
    fn apply_config(&self, contents: &str, summary: &str) -> zbus::Result<u64>;

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
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct License {
    pub name: String,
    #[serde(default)]
    pub url: String,
}

/// Connects to the system bus, or the session bus if `TULSI_BUS=session`.
pub async fn connect() -> zbus::Result<zbus::Connection> {
    if std::env::var(BUS_ENV).as_deref() == Ok("session") {
        zbus::Connection::session().await
    } else {
        zbus::Connection::system().await
    }
}
