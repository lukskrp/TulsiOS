//! Which `configuration.nix` edits a NixOS rollback fully undoes (ADR 0014).
//!
//! An edit is *reversible* when every setting it adds, changes or removes only selects
//! software or switches a feature on or off. Then `tulsi undo`, or booting the previous
//! generation, restores the system completely, and no code of the editor's choosing runs
//! as root or ends up on the user's `PATH`. Such edits use polkit `org.tulsi.apply`, which
//! Starah lets an agent at level 2 (Routine) do on its own.
//!
//! Everything else can reach outside the generation: accounts, boot, file systems,
//! activation scripts, service code, imports, inline scripts, and so on. Those use
//! `org.tulsi.configure`, which asks the human.
//!
//! This is a conservative textual check, not a Nix evaluator. It only allows what it
//! recognises; anything it cannot place counts as not reversible.

use std::collections::BTreeMap;

use crate::local::{find_path_literal, strip_strings_and_comments};

/// Option paths a rollback fully undoes. A pattern matches the path and everything
/// below it.
const REVERSIBLE: &[&str] = &[
    "environment.systemPackages",
    "fonts.packages",
    "fonts.enableDefaultPackages",
    "time.timeZone",
    "i18n.defaultLocale",
    "i18n.extraLocaleSettings",
    "console.keyMap",
    "services.xserver.xkb",
    "networking.hostName",
    "services.printing.drivers",
    "hardware.bluetooth.powerOnBoot",
    "services.avahi.nssmdns4",
];

/// Under these roots, `….enable` switches are reversible: the module's own code (from
/// nixpkgs) runs, not code the editor wrote.
const ENABLE_ROOTS: &[&str] = &["services", "programs", "hardware"];

/// Never reversible, even as an `enable` switch: they guard the machine or open it to
/// others (turning Starah off would unconfine every agent).
const NEVER: &[&str] = &[
    "services.starah",
    "services.openssh",
    "services.getty",
    "services.displayManager.autoLogin",
    "services.xserver.displayManager.autoLogin",
    "services.dbus",
    "services.udev",
    "services.logind",
    "services.journald",
    "programs.nix-ld",
];

/// Names that build or run code of the editor's choosing (inline scripts, wrappers,
/// imports, fetches). A changed line that mentions one is never reversible, even under
/// `environment.systemPackages`: an inline `writeShellScriptBin "ls" …` would run
/// as the user the next time they type `ls`.
const CODE_WORDS: &[&str] = &[
    "import",
    "scopedImport",
    "builtins",
    "callPackage",
    "stdenv",
    "mkDerivation",
    "runCommand",
    "runCommandLocal",
    "runCommandCC",
    "runCommandNoCC",
    "writers",
    "writeShellScript",
    "writeShellScriptBin",
    "writeShellApplication",
    "writeScript",
    "writeScriptBin",
    "writeText",
    "writeTextFile",
    "writeTextDir",
    "writeCBin",
    "symlinkJoin",
    "buildEnv",
    "buildFHSEnv",
    "buildFHSUserEnv",
    "appimageTools",
    "makeWrapper",
    "wrapProgram",
    "override",
    "overrideAttrs",
    "overrideDerivation",
    "fetchurl",
    "fetchzip",
    "fetchgit",
    "fetchGit",
    "fetchTarball",
    "fetchTree",
    "fetchFromGitHub",
    "fetchFromGitLab",
    "fetchClosure",
];

/// One line of the file, with the option path it belongs to.
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
struct Setting {
    path: String,
    /// The line as written (whitespace normalised): what the edit is compared on.
    line: String,
    /// The line with strings and comments blanked: what is checked for code.
    code: String,
    /// The line starts inside a multi-line string (usually a script).
    in_string: bool,
}

/// The settings an edit from `old` to `new` adds, changes or removes that a rollback
/// does not fully undo. The result is sorted and deduplicated; empty means the edit is
/// reversible.
pub fn unreversible_settings(old: &str, new: &str) -> Vec<String> {
    let (Some(old), Some(new)) = (settings(old), settings(new)) else {
        return vec!["(the structure of configuration.nix could not be read)".into()];
    };
    let mut count: BTreeMap<&Setting, i64> = BTreeMap::new();
    for s in &old {
        *count.entry(s).or_default() -= 1;
    }
    for s in &new {
        *count.entry(s).or_default() += 1;
    }
    let mut out: Vec<String> = count
        .into_iter()
        .filter(|(s, n)| *n != 0 && !reversible(s))
        .map(|(s, _)| match (s.in_string, s.path.is_empty()) {
            (true, true) => "(a multi-line string)".to_string(),
            (true, false) => format!("{} (a multi-line string)", s.path),
            (false, true) => "(top level)".to_string(),
            (false, false) => s.path.clone(),
        })
        .collect();
    out.sort();
    out.dedup();
    out
}

fn reversible(s: &Setting) -> bool {
    !s.in_string && path_reversible(&s.path) && code_free(&s.code)
}

fn under(path: &str, pattern: &str) -> bool {
    path == pattern
        || path
            .strip_prefix(pattern)
            .is_some_and(|rest| rest.starts_with('.'))
}

fn path_reversible(path: &str) -> bool {
    if path.is_empty() || NEVER.iter().any(|p| under(path, p)) {
        return false;
    }
    if REVERSIBLE.iter().any(|p| under(path, p)) {
        return true;
    }
    let segments: Vec<&str> = path.split('.').collect();
    segments.len() >= 3
        && ENABLE_ROOTS.contains(&segments[0])
        && segments.last() == Some(&"enable")
        && !segments.contains(&"*")
}

fn code_free(line: &str) -> bool {
    if line.contains("''") || line.contains("${") || find_path_literal(line).is_some() {
        return false;
    }
    !line
        .split(|c: char| !(c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '\''))
        .any(|word| CODE_WORDS.contains(&word))
}

fn is_ident_start(c: char) -> bool {
    c.is_ascii_alphabetic() || c == '_'
}

fn is_ident(c: char) -> bool {
    c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '\''
}

fn join(prefix: &str, path: &str) -> String {
    if prefix.is_empty() {
        path.to_string()
    } else {
        format!("{prefix}.{path}")
    }
}

/// Every non-trivial line of `src` with the option path it sets or belongs to; None if
/// the brackets do not balance.
fn settings(src: &str) -> Option<Vec<Setting>> {
    let code = strip_strings_and_comments(src);
    if code.lines().count() != src.lines().count() {
        return None;
    }
    let mut stack: Vec<String> = Vec::new();
    let mut pending: Option<String> = None;
    // `with pkgs;` / `assert …;` end in a `;` that does not end the setting.
    let mut prefix_statement = false;
    let mut in_indented = false;
    let mut out = Vec::new();

    for (written, raw) in src.lines().zip(code.lines()) {
        let at_start = stack.last().cloned().unwrap_or_default();
        let started_in_string = in_indented;
        let mut line_path: Option<String> = None;
        let chars: Vec<char> = raw.chars().collect();
        let mut i = 0;
        while i < chars.len() {
            let c = chars[i];
            if c == '\'' && chars.get(i + 1) == Some(&'\'') {
                // Stripping keeps only the delimiters of indented strings.
                in_indented = !in_indented;
                i += 2;
                continue;
            }
            if in_indented {
                i += 1;
                continue;
            }
            if is_ident_start(c) || c == '"' {
                // An attribute path: name(.name | ."…")*
                let mut segments = Vec::new();
                loop {
                    if chars.get(i) == Some(&'"') {
                        let end = chars[i + 1..].iter().position(|&c| c == '"')?;
                        i += end + 2;
                        segments.push("*".to_string());
                    } else if chars.get(i).is_some_and(|&c| is_ident_start(c)) {
                        let start = i;
                        while chars.get(i).is_some_and(|&c| is_ident(c)) {
                            i += 1;
                        }
                        segments.push(chars[start..i].iter().collect());
                    } else {
                        break;
                    }
                    if chars.get(i) == Some(&'.')
                        && chars
                            .get(i + 1)
                            .is_some_and(|&c| is_ident_start(c) || c == '"')
                    {
                        i += 1;
                    } else {
                        break;
                    }
                }
                let mut j = i;
                while chars.get(j).is_some_and(|c| c.is_whitespace()) {
                    j += 1;
                }
                if chars.get(j) == Some(&'=') && chars.get(j + 1) != Some(&'=') {
                    let prefix = stack.last().cloned().unwrap_or_default();
                    let full = join(&prefix, &segments.join("."));
                    line_path.get_or_insert_with(|| full.clone());
                    pending = Some(full);
                    i = j + 1;
                } else if segments.len() == 1 && (segments[0] == "with" || segments[0] == "assert")
                {
                    prefix_statement = true;
                }
                continue;
            }
            match c {
                '{' | '[' | '(' => {
                    let prefix = stack.last().cloned().unwrap_or_default();
                    stack.push(pending.take().unwrap_or(prefix));
                }
                '}' | ']' | ')' => {
                    stack.pop()?;
                    pending = None;
                }
                ';' if prefix_statement => prefix_statement = false,
                ';' => pending = None,
                _ => {}
            }
            i += 1;
        }
        let normal = |s: &str| s.split_whitespace().collect::<Vec<_>>().join(" ");
        let line = normal(written);
        let code = normal(raw);
        // Comments and lone brackets change nothing; text inside a script does.
        let meaningful = if started_in_string {
            !line.is_empty()
        } else {
            code.chars().any(|c| c.is_ascii_alphanumeric() || c == '"')
        };
        if meaningful {
            out.push(Setting {
                path: line_path.unwrap_or(at_start),
                line,
                code,
                in_string: started_in_string,
            });
        }
    }
    (stack.is_empty() && !in_indented).then_some(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    const BASE: &str = r#"
{ config, pkgs, ... }:
{
  imports = [ ./hardware-configuration.nix ];

  boot.loader.systemd-boot.enable = true;
  networking.hostName = "tulsi";
  time.timeZone = "Europe/Stockholm";

  users.users.alice = {
    isNormalUser = true;
    extraGroups = [ "wheel" ];
  };

  services.printing.enable = false;
  environment.systemPackages = with pkgs; [
    vim
    git
  ];

  system.stateVersion = "25.05";
}
"#;

    fn edit(from: &str, to: &str) -> Vec<String> {
        assert!(BASE.contains(from), "{from}");
        unreversible_settings(BASE, &BASE.replace(from, to))
    }

    #[test]
    fn unchanged_is_reversible() {
        assert!(unreversible_settings(BASE, BASE).is_empty());
    }

    #[test]
    fn packages_and_feature_switches_are_reversible() {
        assert_eq!(
            edit("    git\n", "    git\n    vlc\n"),
            Vec::<String>::new()
        );
        assert_eq!(
            edit(
                "services.printing.enable = false;",
                "services.printing.enable = true;"
            ),
            Vec::<String>::new()
        );
        assert_eq!(
            edit(
                "  services.printing.enable = false;\n",
                "  services.printing.enable = false;\n  hardware.bluetooth.enable = true;\n  \
                 services.xserver.xkb.layout = \"se\";\n  programs.firefox.enable = true;\n"
            ),
            Vec::<String>::new()
        );
        assert_eq!(
            edit(
                "time.timeZone = \"Europe/Stockholm\";",
                "time.timeZone = \"Asia/Kolkata\";"
            ),
            Vec::<String>::new()
        );
        // Removing a package is just as reversible.
        assert_eq!(edit("    vim\n", ""), Vec::<String>::new());
    }

    #[test]
    fn nested_blocks_know_their_path() {
        let base = "{ ... }:\n{\n  services.printing = {\n    enable = false;\n  };\n}\n";
        let new = base.replace("enable = false", "enable = true");
        assert_eq!(unreversible_settings(base, &new), Vec::<String>::new());
        let new = base.replace("enable = false;", "enable = false;\n    extraConf = \"x\";");
        assert_eq!(
            unreversible_settings(base, &new),
            vec!["services.printing.extraConf"]
        );
    }

    #[test]
    fn accounts_boot_and_state_ask() {
        assert_eq!(
            edit(
                "isNormalUser = true;",
                "isNormalUser = true;\n    extraGroups = [ \"docker\" ];"
            ),
            vec!["users.users.alice.extraGroups"]
        );
        assert_eq!(
            edit(
                "  services.printing",
                "  users.users.bob.isNormalUser = true;\n  services.printing"
            ),
            vec!["users.users.bob.isNormalUser"]
        );
        assert_eq!(
            edit(
                "boot.loader.systemd-boot.enable = true;",
                "boot.loader.grub.enable = true;"
            ),
            vec!["boot.loader.grub.enable", "boot.loader.systemd-boot.enable"]
        );
        assert_eq!(edit("\"25.05\"", "\"25.11\""), vec!["system.stateVersion"]);
        assert_eq!(
            edit(
                "  services.printing",
                "  system.activationScripts.x.text = \"rm -rf /home\";\n  services.printing"
            ),
            vec!["system.activationScripts.x.text"]
        );
        assert_eq!(
            edit(
                "  services.printing",
                "  imports = [ ./evil.nix ];\n  services.printing"
            ),
            vec!["imports"]
        );
    }

    #[test]
    fn guards_never_count_as_switches() {
        assert_eq!(
            edit(
                "  services.printing",
                "  services.starah.enable = false;\n  services.printing"
            ),
            vec!["services.starah.enable"]
        );
        assert_eq!(
            edit(
                "  services.printing",
                "  services.openssh.enable = true;\n  services.printing"
            ),
            vec!["services.openssh.enable"]
        );
    }

    #[test]
    fn inline_code_is_never_reversible() {
        for bad in [
            "    (pkgs.writeShellScriptBin \"ls\" \"rm -rf ~\")\n",
            "    (pkgs.vim.overrideAttrs (o: { }))\n",
            "    (import ./x.nix)\n",
            "    (pkgs.callPackage ./x.nix { })\n",
            "    (builtins.fetchTarball \"https://example.com/x.tgz\")\n",
        ] {
            assert_eq!(
                edit("    git\n", &format!("    git\n{bad}")),
                vec!["environment.systemPackages"],
                "{bad}"
            );
        }
        assert_eq!(
            edit(
                "services.printing.enable = false;",
                "services.printing.enable = builtins.pathExists /etc/x;"
            ),
            vec!["services.printing.enable"]
        );
    }

    #[test]
    fn editing_the_body_of_an_existing_script_asks() {
        let base = "{ pkgs, ... }:\n{\n  environment.systemPackages = [\n    \
                    (pkgs.writeShellScriptBin \"hi\" ''\n      echo hi\n    '')\n  ];\n}\n";
        let new = base.replace("echo hi", "rm -rf ~");
        assert_eq!(
            unreversible_settings(base, &new),
            vec!["environment.systemPackages (a multi-line string)"]
        );
        // A string value changing is a change too (strings are not blanked for the diff).
        let base = "{ ... }:\n{\n  system.activationScripts.x.text = \"echo hi\";\n}\n";
        let new = base.replace("echo hi", "rm -rf /home");
        assert_eq!(
            unreversible_settings(base, &new),
            vec!["system.activationScripts.x.text"]
        );
    }

    #[test]
    fn unknown_options_and_broken_structure_ask() {
        assert_eq!(
            edit(
                "  services.printing",
                "  nixpkgs.config.allowUnfree = true;\n  services.printing"
            ),
            vec!["nixpkgs.config.allowUnfree"]
        );
        assert_eq!(
            unreversible_settings(BASE, "{ ... }: { x = { ; }"),
            vec!["(the structure of configuration.nix could not be read)"]
        );
        // A new file: the function header itself is new.
        assert_eq!(
            unreversible_settings("", "{ pkgs, ... }:\n{\n  time.timeZone = \"UTC\";\n}\n"),
            vec!["(top level)"]
        );
    }
}
