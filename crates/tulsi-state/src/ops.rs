//! Change operations on a [`State`].
//!
//! Every tool (CLI, Software Center, Assistant, browser bridge) expresses a
//! change as a list of `Op`s and sends it to tulsid, which applies them here.
//! On the wire an op is JSON, e.g. `{"op":"addPackage","name":"vlc"}`.

use serde::{Deserialize, Serialize};

use crate::{Error, Service, State};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Browser {
    Firefox,
    Chromium,
}

impl Browser {
    pub fn name(self) -> &'static str {
        match self {
            Browser::Firefox => "firefox",
            Browser::Chromium => "chromium",
        }
    }
}

impl std::str::FromStr for Browser {
    type Err = String;
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "firefox" => Ok(Browser::Firefox),
            "chromium" | "chrome" | "brave" => Ok(Browser::Chromium),
            other => Err(format!(
                "unknown browser {other:?} (expected firefox or chromium)"
            )),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "op", rename_all = "camelCase", deny_unknown_fields)]
pub enum Op {
    AddPackage {
        name: String,
    },
    RemovePackage {
        name: String,
    },
    AddExtension {
        browser: Browser,
        id: String,
    },
    RemoveExtension {
        browser: Browser,
        id: String,
    },
    SetService {
        name: String,
        enable: bool,
    },
    /// A person accepts the licence of an allow-listed unfree package.
    AcceptLicense {
        name: String,
    },
    /// Adds a package made on this machine and installs it. `expression` is a
    /// callPackage-style Nix expression, written to `tulsi/pkgs/<name>/package.nix`
    /// by tulsid (which also checks it); `origin` is where the software came from.
    AddLocalPackage {
        name: String,
        expression: String,
        #[serde(default)]
        version: String,
        #[serde(default)]
        description: String,
        #[serde(default)]
        origin: String,
        /// Keep the downloaded file it is built from (`keepSources`); on unless said
        /// otherwise, so it can always be rebuilt.
        #[serde(default = "yes", rename = "keepSource")]
        keep_source: bool,
    },
    /// Uninstalls a local package and deletes its expression.
    RemoveLocalPackage {
        name: String,
    },
    /// Keeps a local package's downloaded file, or lets Nix's cleanup remove it once
    /// no system generation needs it.
    KeepSource {
        name: String,
        keep: bool,
    },
}

fn yes() -> bool {
    true
}

impl Op {
    /// Short human description, used for commit messages and UIs.
    pub fn describe(&self) -> String {
        match self {
            Op::AddPackage { name } => format!("install {name}"),
            Op::RemovePackage { name } => format!("remove {name}"),
            Op::AddExtension { browser, id } => format!("add {} extension {id}", browser.name()),
            Op::RemoveExtension { browser, id } => {
                format!("remove {} extension {id}", browser.name())
            }
            Op::SetService { name, enable: true } => format!("enable service {name}"),
            Op::SetService {
                name,
                enable: false,
            } => format!("disable service {name}"),
            Op::AcceptLicense { name } => format!("accept the licence of {name}"),
            Op::AddLocalPackage { name, .. } => format!("add local package {name}"),
            Op::RemoveLocalPackage { name } => format!("remove local package {name}"),
            Op::KeepSource { name, keep: true } => format!("keep the download of {name}"),
            Op::KeepSource { name, keep: false } => {
                format!("stop keeping the download of {name}")
            }
        }
    }
}

/// Joins op descriptions into one line, e.g. "install vlc, install gimp".
pub fn describe_all(ops: &[Op]) -> String {
    ops.iter().map(Op::describe).collect::<Vec<_>>().join(", ")
}

impl State {
    /// `ops` as they are meant: removing a package made on this computer
    /// (`tulsi remove frob`, the Software Center's Remove) is removing the local
    /// package, so its record, its kept download and `tulsi/pkgs/<name>` go too.
    pub fn resolve_ops(&self, ops: Vec<Op>) -> Vec<Op> {
        ops.into_iter()
            .map(|op| match op {
                Op::RemovePackage { name } if self.local_packages.contains(&name) => {
                    Op::RemoveLocalPackage { name }
                }
                op => op,
            })
            .collect()
    }

    /// Returns a new state with `ops` applied, validated. Adding something
    /// already present is a no-op; removing something absent is an error so
    /// typos are reported instead of silently ignored.
    pub fn with_ops(&self, ops: &[Op]) -> Result<State, Error> {
        let mut next = self.clone();
        let mut problems = Vec::new();

        for op in ops {
            match op {
                Op::AddPackage { name } => add(&mut next.packages, name),
                Op::RemovePackage { name } => {
                    if !remove(&mut next.packages, name) {
                        problems.push(format!("package {name:?} is not installed by TulsiOS"));
                    }
                }
                Op::AddExtension { browser, id } => add(next.extensions_mut(*browser), id),
                Op::RemoveExtension { browser, id } => {
                    if !remove(next.extensions_mut(*browser), id) {
                        problems.push(format!(
                            "{} extension {id:?} is not installed",
                            browser.name()
                        ));
                    }
                }
                Op::SetService { name, enable } => {
                    next.services
                        .insert(name.clone(), Service { enable: *enable });
                }
                Op::AcceptLicense { name } => add(&mut next.accepted_licenses, name),
                Op::AddLocalPackage {
                    name, keep_source, ..
                } => {
                    add(&mut next.local_packages, name);
                    add(&mut next.packages, name);
                    if *keep_source {
                        add(&mut next.keep_sources, name);
                    } else {
                        remove(&mut next.keep_sources, name);
                    }
                }
                Op::RemoveLocalPackage { name } => {
                    if !remove(&mut next.local_packages, name) {
                        problems.push(format!("{name:?} is not a local package"));
                    }
                    remove(&mut next.packages, name);
                    remove(&mut next.keep_sources, name);
                }
                Op::KeepSource { name, keep } => {
                    if !next.local_packages.contains(name) {
                        problems.push(format!("{name:?} is not a local package"));
                    } else if *keep {
                        add(&mut next.keep_sources, name);
                    } else {
                        remove(&mut next.keep_sources, name);
                    }
                }
            }
        }

        if !problems.is_empty() {
            return Err(Error::Invalid(problems));
        }
        next.validate()?;
        Ok(next)
    }

    /// Human-readable differences from `self` to `other`, one line each,
    /// prefixed with `+` (added/enabled) or `-` (removed/disabled).
    pub fn diff(&self, other: &State) -> Vec<String> {
        let mut out = Vec::new();
        list_diff(
            &mut out,
            "licence accepted:",
            &self.accepted_licenses,
            &other.accepted_licenses,
        );
        list_diff(
            &mut out,
            "local package",
            &self.local_packages,
            &other.local_packages,
        );
        list_diff(&mut out, "package", &self.packages, &other.packages);
        list_diff(
            &mut out,
            "kept download:",
            &self.keep_sources,
            &other.keep_sources,
        );
        list_diff(
            &mut out,
            "firefox extension",
            &self.browser_extensions.firefox,
            &other.browser_extensions.firefox,
        );
        list_diff(
            &mut out,
            "chromium extension",
            &self.browser_extensions.chromium,
            &other.browser_extensions.chromium,
        );
        for (name, svc) in &other.services {
            if self.services.get(name) != Some(svc) {
                let sign = if svc.enable { '+' } else { '-' };
                let verb = if svc.enable { "enabled" } else { "disabled" };
                out.push(format!("{sign} service {name} {verb}"));
            }
        }
        for name in self.services.keys() {
            if !other.services.contains_key(name) {
                out.push(format!("- service {name} unmanaged"));
            }
        }
        out
    }

    /// `self` with an earlier change (`before` → `after`) taken back, by meaning
    /// rather than by text: what that change added is removed, what it removed is
    /// added back, and services it switched are switched back. Whatever a later
    /// change already altered is left alone, so this never conflicts.
    pub fn reverted(&self, before: &State, after: &State) -> State {
        let mut next = self.clone();
        revert_list(&mut next.packages, &before.packages, &after.packages);
        revert_list(
            &mut next.local_packages,
            &before.local_packages,
            &after.local_packages,
        );
        revert_list(
            &mut next.accepted_licenses,
            &before.accepted_licenses,
            &after.accepted_licenses,
        );
        revert_list(
            &mut next.keep_sources,
            &before.keep_sources,
            &after.keep_sources,
        );
        // A kept download whose package the revert took away goes with it.
        let locals = next.local_packages.clone();
        next.keep_sources.retain(|n| locals.contains(n));
        revert_list(
            &mut next.browser_extensions.firefox,
            &before.browser_extensions.firefox,
            &after.browser_extensions.firefox,
        );
        revert_list(
            &mut next.browser_extensions.chromium,
            &before.browser_extensions.chromium,
            &after.browser_extensions.chromium,
        );
        let names: std::collections::BTreeSet<&String> = before
            .services
            .keys()
            .chain(after.services.keys())
            .collect();
        for name in names {
            let (was, became) = (before.services.get(name), after.services.get(name));
            // Only if that change switched it, and nothing switched it since.
            if was == became || next.services.get(name) != became {
                continue;
            }
            match was {
                Some(svc) => {
                    next.services.insert(name.clone(), svc.clone());
                }
                None => {
                    next.services.remove(name);
                }
            }
        }
        next
    }

    fn extensions_mut(&mut self, browser: Browser) -> &mut Vec<String> {
        match browser {
            Browser::Firefox => &mut self.browser_extensions.firefox,
            Browser::Chromium => &mut self.browser_extensions.chromium,
        }
    }
}

fn add(list: &mut Vec<String>, item: &str) {
    if !list.iter().any(|x| x == item) {
        list.push(item.to_string());
    }
}

fn remove(list: &mut Vec<String>, item: &str) -> bool {
    let before = list.len();
    list.retain(|x| x != item);
    list.len() != before
}

/// Takes back one change to a list: removes what it added, re-adds what it removed.
fn revert_list(current: &mut Vec<String>, before: &[String], after: &[String]) {
    for item in after.iter().filter(|x| !before.contains(x)) {
        remove(current, item);
    }
    for item in before.iter().filter(|x| !after.contains(x)) {
        add(current, item);
    }
}

fn list_diff(out: &mut Vec<String>, what: &str, old: &[String], new: &[String]) {
    for item in new.iter().filter(|x| !old.contains(x)) {
        out.push(format!("+ {what} {item}"));
    }
    for item in old.iter().filter(|x| !new.contains(x)) {
        out.push(format!("- {what} {item}"));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ops(json: &str) -> Vec<Op> {
        serde_json::from_str(json).unwrap()
    }

    #[test]
    fn parses_wire_format() {
        let parsed = ops(r#"[{"op":"addPackage","name":"vlc"},
            {"op":"addExtension","browser":"firefox","id":"uBlock0@raymondhill.net"},
            {"op":"setService","name":"docker","enable":true}]"#);
        assert_eq!(parsed.len(), 3);
        assert_eq!(
            describe_all(&parsed),
            "install vlc, add firefox extension uBlock0@raymondhill.net, enable service docker"
        );
    }

    #[test]
    fn apply_and_diff() {
        let base = State::default();
        let next = base
            .with_ops(&ops(
                r#"[{"op":"addPackage","name":"vlc"},{"op":"addPackage","name":"vlc"},
                {"op":"setService","name":"docker","enable":true}]"#,
            ))
            .unwrap();
        assert_eq!(next.packages, vec!["vlc"]);
        assert_eq!(
            base.diff(&next),
            vec!["+ package vlc", "+ service docker enabled"]
        );
        assert_eq!(
            next.diff(&base),
            vec!["- package vlc", "- service docker unmanaged"]
        );
        assert!(next.diff(&next).is_empty());
    }

    #[test]
    fn reverting_an_older_change_keeps_later_ones() {
        let s0 = State::default();
        let s1 = s0
            .with_ops(&ops(r#"[{"op":"addPackage","name":"cowsay"}]"#))
            .unwrap();
        let s2 = s1
            .with_ops(&ops(
                r#"[{"op":"addPackage","name":"hello"},{"op":"setService","name":"printing","enable":true}]"#,
            ))
            .unwrap();
        // Undo the first change (cowsay) on top of the second.
        let undone = s2.reverted(&s0, &s1);
        assert_eq!(undone.packages, vec!["hello"]);
        assert!(undone.services["printing"].enable);
        // Undo the second change: hello goes, printing is unmanaged again.
        let undone = s2.reverted(&s1, &s2);
        assert_eq!(undone, s1);
    }

    #[test]
    fn reverting_what_a_later_change_already_altered_does_nothing() {
        let s0 = State::default();
        let s1 = s0
            .with_ops(&ops(
                r#"[{"op":"addPackage","name":"vlc"},{"op":"setService","name":"printing","enable":true}]"#,
            ))
            .unwrap();
        let s2 = s1
            .with_ops(&ops(
                r#"[{"op":"removePackage","name":"vlc"},{"op":"setService","name":"printing","enable":false}]"#,
            ))
            .unwrap();
        assert_eq!(s2.reverted(&s0, &s1), s2);
        // Undoing a removal adds it back.
        let s3 = s2.reverted(&s1, &s2);
        assert_eq!(s3.packages, vec!["vlc"]);
        assert!(s3.services["printing"].enable);
    }

    #[test]
    fn removing_missing_is_an_error() {
        let err = State::default()
            .with_ops(&ops(r#"[{"op":"removePackage","name":"vlc"}]"#))
            .unwrap_err();
        assert!(err.to_string().contains("not installed"), "{err}");
    }

    #[test]
    fn invalid_names_are_rejected() {
        assert!(State::default()
            .with_ops(&ops(r#"[{"op":"addPackage","name":"rm -rf /"}]"#))
            .is_err());
        assert!(State::default()
            .with_ops(&ops(
                r#"[{"op":"addExtension","browser":"chromium","id":"short"}]"#
            ))
            .is_err());
    }

    #[test]
    fn accept_license_is_recorded_and_diffed_first() {
        let base = State::default();
        let next = base
            .with_ops(&ops(r#"[{"op":"acceptLicense","name":"claude-code"},
                    {"op":"addPackage","name":"claude-code"}]"#))
            .unwrap();
        assert_eq!(next.accepted_licenses, vec!["claude-code"]);
        assert_eq!(
            base.diff(&next),
            vec!["+ licence accepted: claude-code", "+ package claude-code"]
        );
        // Older state files without the field still load, and stay without it.
        let json = base.to_json_pretty();
        assert!(!json.contains("acceptedLicenses"), "{json}");
        assert!(next.to_json_pretty().contains("\"acceptedLicenses\""));
    }

    #[test]
    fn local_packages_are_recorded_installed_and_removed() {
        let base = State::default();
        let next = base
            .with_ops(&ops(
                r#"[{"op":"addLocalPackage","name":"frob","expression":"{ stdenv }: stdenv.mkDerivation {}",
                     "origin":"https://example.com/frob.tar.gz"}]"#,
            ))
            .unwrap();
        assert_eq!(next.local_packages, vec!["frob"]);
        assert_eq!(next.packages, vec!["frob"]);
        assert_eq!(
            base.diff(&next),
            vec![
                "+ local package frob",
                "+ package frob",
                "+ kept download: frob"
            ]
        );
        let gone = next
            .with_ops(&ops(r#"[{"op":"removeLocalPackage","name":"frob"}]"#))
            .unwrap();
        assert_eq!(gone, base);
        // A plain removePackage of it means the same, once resolved.
        let resolved = next.resolve_ops(ops(
            r#"[{"op":"removePackage","name":"frob"},{"op":"removePackage","name":"vlc"}]"#,
        ));
        assert_eq!(
            describe_all(&resolved),
            "remove local package frob, remove vlc"
        );
        assert_eq!(
            next.with_ops(&resolved[..1]).unwrap(),
            base,
            "record, package and kept download all go"
        );
        assert!(base
            .with_ops(&ops(
                r#"[{"op":"addLocalPackage","name":"Bad/Name","expression":"x"}]"#
            ))
            .is_err());
    }

    #[test]
    fn rejects_unknown_ops() {
        assert!(serde_json::from_str::<Vec<Op>>(r#"[{"op":"runShell","cmd":"x"}]"#).is_err());
    }

    #[test]
    fn downloads_are_kept_by_choice() {
        let base = State::default();
        // Kept unless said otherwise.
        let kept = base
            .with_ops(&ops(
                r#"[{"op":"addLocalPackage","name":"frob","expression":"{ }: x"}]"#,
            ))
            .unwrap();
        assert_eq!(kept.keep_sources, vec!["frob"]);
        assert_eq!(
            base.diff(&kept),
            vec![
                "+ local package frob",
                "+ package frob",
                "+ kept download: frob"
            ]
        );
        let not = base
            .with_ops(&ops(
                r#"[{"op":"addLocalPackage","name":"frob","expression":"{ }: x","keepSource":false}]"#,
            ))
            .unwrap();
        assert!(not.keep_sources.is_empty());
        // Changed later, and undone.
        let off = kept
            .with_ops(&ops(r#"[{"op":"keepSource","name":"frob","keep":false}]"#))
            .unwrap();
        assert!(off.keep_sources.is_empty());
        assert_eq!(off.reverted(&kept, &off).keep_sources, vec!["frob"]);
        // Only local packages; removing one stops keeping its download.
        assert!(base
            .with_ops(&ops(r#"[{"op":"keepSource","name":"vlc","keep":true}]"#))
            .is_err());
        let gone = kept
            .with_ops(&ops(r#"[{"op":"removeLocalPackage","name":"frob"}]"#))
            .unwrap();
        assert!(gone.keep_sources.is_empty());
        // Undoing the add takes the kept download away with the package.
        assert!(kept.reverted(&base, &kept).keep_sources.is_empty());
    }
}
