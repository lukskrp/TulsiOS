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
    AddPackage { name: String },
    RemovePackage { name: String },
    AddExtension { browser: Browser, id: String },
    RemoveExtension { browser: Browser, id: String },
    SetService { name: String, enable: bool },
    /// A person accepts the licence of an allow-listed unfree package.
    AcceptLicense { name: String },
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
    },
    /// Uninstalls a local package and deletes its expression.
    RemoveLocalPackage { name: String },
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
        }
    }
}

/// Joins op descriptions into one line, e.g. "install vlc, install gimp".
pub fn describe_all(ops: &[Op]) -> String {
    ops.iter().map(Op::describe).collect::<Vec<_>>().join(", ")
}

impl State {
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
                Op::AddLocalPackage { name, .. } => {
                    add(&mut next.local_packages, name);
                    add(&mut next.packages, name);
                }
                Op::RemoveLocalPackage { name } => {
                    if !remove(&mut next.local_packages, name) {
                        problems.push(format!("{name:?} is not a local package"));
                    }
                    remove(&mut next.packages, name);
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
            .with_ops(&ops(
                r#"[{"op":"acceptLicense","name":"claude-code"},
                    {"op":"addPackage","name":"claude-code"}]"#,
            ))
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
            vec!["+ local package frob", "+ package frob"]
        );
        let gone = next
            .with_ops(&ops(r#"[{"op":"removeLocalPackage","name":"frob"}]"#))
            .unwrap();
        assert_eq!(gone, base);
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
}
