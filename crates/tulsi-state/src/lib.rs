//! The TulsiOS declarative state file (`state.json`).
//!
//! This is the single contract between TulsiOS tools (daemon, CLI, Software
//! Center, Assistant, browser bridge) and the `tulsi.state` NixOS module.
//! Keep it in sync with `state/schema.json`.

use std::collections::{BTreeMap, HashSet};
use std::path::Path;

use serde::{Deserialize, Serialize};

mod local;
mod ops;
mod reach;
pub use local::check_expression;
pub use ops::{describe_all, Browser, Op};
pub use reach::unreversible_settings;

pub const CURRENT_VERSION: u32 = 1;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct State {
    pub version: u32,
    #[serde(default)]
    pub packages: Vec<String>,
    #[serde(default)]
    pub browser_extensions: BrowserExtensions,
    #[serde(default)]
    pub services: BTreeMap<String, Service>,
    /// Unfree packages whose licence a person accepted (in the Software Center).
    /// Only packages tulsid's allow-list names can be accepted; the tulsi.state module
    /// allows exactly these through nixpkgs.config.allowUnfreePredicate.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub accepted_licenses: Vec<String>,
    /// Packages made on this machine (by a person or the packaging agent): their
    /// expressions live in `tulsi/pkgs/<name>/package.nix` next to state.json. Each is
    /// also in `packages` while installed.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub local_packages: Vec<String>,
    /// Local packages whose downloaded file is kept (ADR 0018): the tulsi.state module
    /// makes it part of the system, so Nix's cleanup leaves it while a generation
    /// uses it and the package can always be rebuilt (after an upgrade, say).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub keep_sources: Vec<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BrowserExtensions {
    #[serde(default)]
    pub firefox: Vec<String>,
    #[serde(default)]
    pub chromium: Vec<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Service {
    #[serde(default)]
    pub enable: bool,
}

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("cannot read {path}: {source}")]
    Io {
        path: String,
        source: std::io::Error,
    },
    #[error("invalid JSON: {0}")]
    Json(#[from] serde_json::Error),
    #[error("state is invalid:\n  - {}", .0.join("\n  - "))]
    Invalid(Vec<String>),
}

impl Default for State {
    fn default() -> Self {
        Self {
            version: CURRENT_VERSION,
            packages: Vec::new(),
            browser_extensions: BrowserExtensions::default(),
            services: BTreeMap::new(),
            accepted_licenses: Vec::new(),
            local_packages: Vec::new(),
            keep_sources: Vec::new(),
        }
    }
}

impl State {
    pub fn from_json(text: &str) -> Result<Self, Error> {
        let state: State = serde_json::from_str(text)?;
        state.validate()?;
        Ok(state)
    }

    pub fn load(path: &Path) -> Result<Self, Error> {
        let text = std::fs::read_to_string(path).map_err(|source| Error::Io {
            path: path.display().to_string(),
            source,
        })?;
        Self::from_json(&text)
    }

    pub fn to_json_pretty(&self) -> String {
        let mut out = serde_json::to_string_pretty(self).expect("State always serializes");
        out.push('\n');
        out
    }

    /// Collects every problem instead of stopping at the first one, so UIs
    /// can show them all at once.
    pub fn validate(&self) -> Result<(), Error> {
        let mut problems = Vec::new();

        if self.version != CURRENT_VERSION {
            problems.push(format!(
                "unsupported version {} (expected {CURRENT_VERSION})",
                self.version
            ));
        }
        check_list(&mut problems, "package", &self.packages, is_valid_attr_path);
        check_list(
            &mut problems,
            "local package",
            &self.local_packages,
            is_valid_local_name,
        );
        check_list(
            &mut problems,
            "accepted licence",
            &self.accepted_licenses,
            is_valid_attr_path,
        );
        check_list(
            &mut problems,
            "Firefox extension id",
            &self.browser_extensions.firefox,
            is_valid_firefox_id,
        );
        check_list(
            &mut problems,
            "Chromium extension id",
            &self.browser_extensions.chromium,
            is_valid_chromium_id,
        );
        for name in self.services.keys() {
            if !is_valid_identifier(name) || name.contains('\'') {
                problems.push(format!("invalid service name {name:?}"));
            }
        }
        for name in &self.keep_sources {
            if !self.local_packages.contains(name) {
                problems.push(format!(
                    "the download of {name:?} is kept, but it is not a local package"
                ));
            }
        }

        if problems.is_empty() {
            Ok(())
        } else {
            Err(Error::Invalid(problems))
        }
    }
}

fn check_list(problems: &mut Vec<String>, what: &str, items: &[String], ok: fn(&str) -> bool) {
    let mut seen = HashSet::new();
    for item in items {
        if !ok(item) {
            problems.push(format!("invalid {what} {item:?}"));
        }
        if !seen.insert(item) {
            problems.push(format!("duplicate {what} {item:?}"));
        }
    }
}

fn is_valid_identifier(s: &str) -> bool {
    let mut chars = s.chars();
    matches!(chars.next(), Some(c) if c.is_ascii_alphabetic() || c == '_')
        && chars.all(|c| c.is_ascii_alphanumeric() || matches!(c, '_' | '-' | '\''))
}

/// A local package name: one lowercase identifier (it is also a directory name).
pub fn is_valid_local_name(s: &str) -> bool {
    let mut chars = s.chars();
    matches!(chars.next(), Some(c) if c.is_ascii_lowercase())
        && s.len() <= 64
        && chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-')
}

/// `vlc`, `python3Packages.requests`, `gnome-text-editor`.
pub fn is_valid_attr_path(s: &str) -> bool {
    !s.is_empty() && s.split('.').all(is_valid_identifier)
}

/// `{8-4-4-4-12 uuid}` or an email-like id such as `uBlock0@raymondhill.net`.
pub fn is_valid_firefox_id(s: &str) -> bool {
    if let Some(inner) = s.strip_prefix('{').and_then(|r| r.strip_suffix('}')) {
        return inner.len() == 36 && inner.chars().all(|c| c.is_ascii_hexdigit() || c == '-');
    }
    match s.split_once('@') {
        Some((local, domain)) => {
            local
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | '+' | '-'))
                && !domain.is_empty()
                && domain
                    .chars()
                    .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | '-'))
        }
        None => false,
    }
}

/// Chrome Web Store ids are 32 characters in the range `a`..=`p`.
pub fn is_valid_chromium_id(s: &str) -> bool {
    s.len() == 32 && s.bytes().all(|b| (b'a'..=b'p').contains(&b))
}

#[cfg(test)]
mod tests {
    use super::*;

    const EXAMPLE: &str = include_str!("../../../state/example.json");

    #[test]
    fn example_state_is_valid() {
        let state = State::from_json(EXAMPLE).unwrap();
        assert!(state.packages.contains(&"vlc".to_string()));
    }

    #[test]
    fn round_trips() {
        let state = State::from_json(EXAMPLE).unwrap();
        assert_eq!(State::from_json(&state.to_json_pretty()).unwrap(), state);
    }

    #[test]
    fn rejects_bad_entries() {
        let text = r#"{"version":1,"packages":["vlc","vlc","rm -rf"],
            "browserExtensions":{"firefox":["nope"],"chromium":["xyz"]}}"#;
        let Err(Error::Invalid(problems)) = State::from_json(text) else {
            panic!("expected validation failure");
        };
        assert_eq!(problems.len(), 4, "{problems:?}");
    }

    #[test]
    fn rejects_unknown_fields() {
        assert!(State::from_json(r#"{"version":1,"pakages":[]}"#).is_err());
    }

    #[test]
    fn id_formats() {
        assert!(is_valid_attr_path("python3Packages.requests"));
        assert!(!is_valid_attr_path("a..b"));
        assert!(is_valid_firefox_id("uBlock0@raymondhill.net"));
        assert!(is_valid_firefox_id(
            "{446900e4-71c2-419f-a6a7-df9c091e268b}"
        ));
        assert!(is_valid_chromium_id("cjpalhdlnbpafiamejdnhcphjbkeiagm"));
        assert!(!is_valid_chromium_id("cjpalhdlnbpafiamejdnhcphjbkeiagz"));
    }
}
