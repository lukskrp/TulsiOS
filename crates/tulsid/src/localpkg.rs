//! Packages made on this machine (`tulsi/pkgs/<name>/package.nix` + `meta.json`).
//!
//! The expression is evaluated by the system rebuild, as root. A person reviews it
//! before it is applied (ADR 0013); this module adds a static check as a second line
//! of defence: no reading of host files, no impure fetches, no escaping the build
//! sandbox. Builds themselves run in Nix's sandbox; downloads must be fixed-output
//! (hashed) fetchers such as `fetchurl`.

use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::config::Config;
use crate::git::{self, FileChange};
pub use tulsi_state::check_expression;

/// What the Software Center shows about a local package.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Meta {
    #[serde(default)]
    pub version: String,
    #[serde(default)]
    pub description: String,
    /// Where the software came from (URL or file name).
    #[serde(default)]
    pub origin: String,
}

pub fn package_rel(name: &str) -> String {
    format!("{}/{name}/package.nix", Config::PKGS_REL)
}

pub fn meta_rel(name: &str) -> String {
    format!("{}/{name}/meta.json", Config::PKGS_REL)
}

pub fn read_meta(dir: &Path, name: &str) -> Meta {
    git::read(dir, &meta_rel(name))
        .and_then(|b| serde_json::from_slice(&b).ok())
        .unwrap_or_default()
}

/// The file changes that add (or replace) a local package.
pub fn add_changes(dir: &Path, name: &str, expression: &str, meta: &Meta) -> Vec<FileChange> {
    let package = package_rel(name);
    let meta_path = meta_rel(name);
    let mut meta_json = serde_json::to_vec_pretty(meta).expect("meta serializes");
    meta_json.push(b'\n');
    vec![
        FileChange {
            old: git::read(dir, &package),
            new: Some(expression.as_bytes().to_vec()),
            rel: package,
        },
        FileChange {
            old: git::read(dir, &meta_path),
            new: Some(meta_json),
            rel: meta_path,
        },
    ]
}

/// The file changes that delete a local package.
pub fn remove_changes(dir: &Path, name: &str) -> Vec<FileChange> {
    [package_rel(name), meta_rel(name)]
        .into_iter()
        .map(|rel| FileChange {
            old: git::read(dir, &rel),
            new: None,
            rel,
        })
        .collect()
}
