//! Building a recipe's package as the person who asked: the downloaded file goes
//! into the Nix store, the package into `~/.local/share/tulsi/recipes/<name>/`, and
//! `nix-build` builds it against the system's pinned nixpkgs (`/etc/tulsi/nixpkgs`)
//! in Nix's sandbox. A failed build is read for what can be fixed without a person
//! or a model, and built again:
//! - libraries a prebuilt program needs (`could not satisfy dependency libX.so`),
//!   from data/sonames.json; libraries nobody provides are left out, with a warning;
//! - build dependencies a source build looks for (pkg-config, Meson, CMake names),
//!   from data/pkg-config-names.json;
//! - the hash of a Rust or Go program's dependencies (`got: sha256-…`).
//!
//! Then the main program is started briefly, without a display, in a throwaway home.

use std::collections::{BTreeSet, VecDeque};
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

use crate::{
    expression, package_for_dependency, package_for_soname, store_name, Answers, Fixes, Plan,
    Recipe, Source,
};

/// The system's pinned nixpkgs (set by the TulsiOS flake); `TULSI_NIXPKGS` overrides.
const NIXPKGS: &str = "/etc/tulsi/nixpkgs";
const ATTEMPTS: usize = 5;
const LOG_KEEP: usize = 400;
const TRY_TIMEOUT: Duration = Duration::from_secs(10);

/// Starting the built program.
#[derive(Debug, Clone, Default, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Tried {
    pub program: String,
    /// It started: not a loader error or a missing file.
    pub ok: bool,
    pub output: String,
}

/// What `build` did.
#[derive(Debug, Clone, Default, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Outcome {
    pub ok: bool,
    pub name: String,
    pub version: String,
    pub description: String,
    /// The person said it is proprietary and accepts its licence.
    pub unfree: bool,
    /// Keep the downloaded file as part of the system.
    pub keep_source: bool,
    /// The package (what goes to `addLocalPackage`).
    pub expression: String,
    /// Where it came from, for meta.json: `recipe:<kind> <file>`.
    pub origin: String,
    pub out_path: String,
    /// Programs in the package's bin/.
    pub programs: Vec<String>,
    pub tried: Option<Tried>,
    /// Things people should know (libraries left out, programs that did not start).
    pub warnings: Vec<String>,
    /// Why it failed, for people.
    pub error: String,
    /// The end of the last build's log.
    pub log_tail: String,
    pub draft: String,
}

/// The answers a draft was made with, kept beside it as `recipe.json`, so a draft a
/// person edited (in the Nix Editor, ADR 0019) is built and installed the same way.
#[derive(Debug, Clone, Default, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct DraftInfo {
    pub name: String,
    pub version: String,
    pub description: String,
    pub unfree: bool,
    pub keep_source: bool,
    pub origin: String,
    /// The main program, which is tried.
    pub program: String,
}

pub const DRAFT_INFO: &str = "recipe.json";

fn nix() -> Command {
    let mut c = Command::new("nix");
    c.args(["--extra-experimental-features", "nix-command"]);
    c
}

fn output(cmd: &mut Command) -> Result<String, String> {
    let out = cmd
        .stdin(Stdio::null())
        .output()
        .map_err(|e| format!("cannot run {cmd:?}: {e}"))?;
    if out.status.success() {
        Ok(String::from_utf8_lossy(&out.stdout).trim().to_string())
    } else {
        Err(String::from_utf8_lossy(&out.stderr).trim().to_string())
    }
}

/// Adds `file` to the store under `name`; returns its SRI hash.
fn add_to_store(file: &Path, name: &str, work: &Path) -> Result<String, String> {
    let staged = work.join(name);
    std::fs::copy(file, &staged).map_err(|e| format!("cannot read {}: {e}", file.display()))?;
    output(
        Command::new("nix-store")
            .args(["--add-fixed", "sha256"])
            .arg(&staged),
    )
    .map_err(|e| format!("cannot add the file to the Nix store: {e}"))?;
    let hash = output(
        nix()
            .args(["hash", "file", "--sri", "--type", "sha256"])
            .arg(&staged),
    )
    .map_err(|e| format!("cannot hash the file: {e}"))?;
    let _ = std::fs::remove_file(&staged);
    Ok(hash)
}

fn data_dir() -> PathBuf {
    std::env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|h| Path::new(&h).join(".local/share")))
        .unwrap_or_else(std::env::temp_dir)
        .join("tulsi/recipes")
}

/// What a failed build's log says can be fixed.
#[derive(Debug, Default, PartialEq, Eq)]
pub(crate) struct Findings {
    pub missing_libraries: BTreeSet<String>,
    pub missing_dependencies: BTreeSet<String>,
    pub got_hash: Option<String>,
    pub vendor_folder: bool,
}

pub(crate) fn read_log(lines: &[String]) -> Findings {
    let mut f = Findings::default();
    for line in lines {
        let l = line.trim();
        if let Some(rest) = l.split("could not satisfy dependency ").nth(1) {
            if let Some(lib) = rest.split_whitespace().next() {
                f.missing_libraries.insert(lib.to_string());
            }
        }
        if let Some(h) = l.strip_prefix("got:") {
            f.got_hash = Some(h.trim().to_string());
        }
        if l.contains("vendor folder exists") {
            f.vendor_folder = true;
        }
        // pkg-config: "Package 'gtk+-3.0', required by 'x', not found" / "No package 'x' found"
        for (start, end) in [("Package '", "'"), ("No package '", "'")] {
            if let Some(rest) = l.split(start).nth(1) {
                if let Some(name) = rest.split(end).next() {
                    if l.contains("found") {
                        f.missing_dependencies.insert(name.to_string());
                    }
                }
            }
        }
        // Meson: Dependency "gtk+-3.0" not found
        if let Some(rest) = l.split("Dependency \"").nth(1) {
            if l.contains("not found") {
                if let Some(name) = rest.split('"').next() {
                    f.missing_dependencies.insert(name.to_string());
                }
            }
        }
        // CMake: Could NOT find ZLIB / package configuration file provided by "Qt5"
        if let Some(rest) = l.split("Could NOT find ").nth(1) {
            if let Some(name) = rest.split([' ', '(']).next() {
                f.missing_dependencies.insert(name.to_string());
            }
        }
        if let Some(rest) = l.split("configuration file provided by \"").nth(1) {
            if let Some(name) = rest.split('"').next() {
                f.missing_dependencies.insert(name.to_string());
            }
        }
    }
    f
}

/// Builds `expr_file`; streams the log to `progress`; returns (out path or None, log tail).
fn nix_build(
    expr_file: &Path,
    name: &str,
    progress: &mut dyn FnMut(&str),
) -> Result<(Option<String>, Vec<String>), String> {
    let nixpkgs = std::env::var("TULSI_NIXPKGS").unwrap_or_else(|_| NIXPKGS.to_string());
    // The package (and its downloaded file, named after it) may be unfree: allow
    // exactly this one, as the system does once its licence is accepted.
    let expr = format!(
        "let pkgs = import {nixpkgs} {{ config.allowUnfreePredicate = p: \
         (builtins.parseDrvName (p.name or \"\")).name == \"{name}\" || (p.pname or \"\") == \"{name}\"; }}; \
         in pkgs.callPackage {} {{ }}",
        expr_file.display()
    );
    let mut child = Command::new("nix-build")
        .args(["--no-out-link", "--expr", &expr])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("cannot start nix-build: {e}"))?;
    let stderr = child.stderr.take().expect("piped");
    let mut tail: VecDeque<String> = VecDeque::new();
    let mut findings_lines: Vec<String> = Vec::new();
    for line in BufReader::new(stderr).lines().map_while(Result::ok) {
        progress(&line);
        if line.contains("could not satisfy dependency")
            || line.contains("got:")
            || line.contains("vendor folder exists")
            || line.contains("not found")
            || line.contains("Could NOT find")
            || line.contains("configuration file provided by")
        {
            findings_lines.push(line.clone());
        }
        tail.push_back(line);
        if tail.len() > LOG_KEEP {
            tail.pop_front();
        }
    }
    let out = child.wait_with_output().map_err(|e| e.to_string())?;
    let mut lines: Vec<String> = tail.into_iter().collect();
    lines.extend(findings_lines);
    if out.status.success() {
        let path = String::from_utf8_lossy(&out.stdout)
            .lines()
            .last()
            .unwrap_or_default()
            .trim()
            .to_string();
        Ok((Some(path), lines))
    } else {
        Ok((None, lines))
    }
}

/// bubblewrap from the Nix build (nix/packages/tulsi-tools.nix), else the one on PATH.
const BWRAP: &str = match option_env!("TULSI_BWRAP") {
    Some(path) => path,
    None => "bwrap",
};

/// The sandbox the try runs in: only the read-only Nix store and an empty home; no
/// network, no other processes, none of the person's files or environment. The
/// program comes from a download nobody has reviewed.
fn sandbox(program: &Path, arg: &str) -> Command {
    let mut cmd = Command::new(BWRAP);
    cmd.args([
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--ro-bind",
        "/nix/store",
        "/nix/store",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--tmpfs",
        "/home",
        "--dir",
        "/home/try",
        "--chdir",
        "/home/try",
        "--clearenv",
        "--setenv",
        "HOME",
        "/home/try",
        "--setenv",
        "PATH",
        "/no-path",
        "--",
    ])
    .arg(program)
    .arg(arg);
    cmd
}

/// Whether the sandbox works here (it needs user namespaces), tried with bubblewrap
/// itself, which is in the Nix store.
fn sandbox_works() -> bool {
    let probe = Path::new(BWRAP);
    if !probe.starts_with("/nix/store") {
        return false;
    }
    sandbox(probe, "--version")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .is_ok_and(|s| s.success())
}

/// Starts `program --version` briefly, in the sandbox. Loader errors and missing
/// files fail; anything else (including "cannot open display") counts as started.
/// Without a working sandbox it is not run at all.
fn try_program(bin: &Path) -> Tried {
    let program = bin
        .file_name()
        .map(|f| f.to_string_lossy().into_owned())
        .unwrap_or_default();
    if !sandbox_works() {
        return Tried {
            program,
            ok: false,
            output: "not tried: there is no sandbox to run it in safely".into(),
        };
    }
    let child = sandbox(bin, "--version")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn();
    let mut child = match child {
        Ok(c) => c,
        Err(e) => {
            return Tried {
                program,
                ok: false,
                output: e.to_string(),
            }
        }
    };
    let start = Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(_)) => break,
            Ok(None) if start.elapsed() > TRY_TIMEOUT => {
                // Still running after a while: a program that waits for input or a window.
                let _ = child.kill();
                let _ = child.wait();
                return Tried {
                    program,
                    ok: true,
                    output: "(still running after 10 seconds; stopped)".into(),
                };
            }
            Ok(None) => std::thread::sleep(Duration::from_millis(100)),
            Err(_) => break,
        }
    }
    let out = child.wait_with_output().ok();
    let (code, text) = match &out {
        Some(o) => (
            o.status.code(),
            format!(
                "{}{}",
                String::from_utf8_lossy(&o.stdout),
                String::from_utf8_lossy(&o.stderr)
            ),
        ),
        None => (None, String::new()),
    };
    let broken = matches!(code, Some(126 | 127))
        || text.contains("error while loading shared libraries")
        || text.contains("cannot execute");
    Tried {
        program,
        ok: !broken,
        output: text.chars().take(2000).collect(),
    }
}

/// Builds the package for `file` with `plan` and `answers`, fixing what it can.
pub fn build(
    file: &Path,
    plan: &Plan,
    answers: &Answers,
    progress: &mut dyn FnMut(&str),
) -> Outcome {
    let mut outcome = Outcome {
        name: answers.name.clone(),
        version: answers.version.clone(),
        unfree: answers.unfree,
        keep_source: answers.keep_source,
        description: if answers.description.is_empty() {
            plan.description.clone()
        } else {
            answers.description.clone()
        },
        origin: format!(
            "recipe:{} {}",
            serde_json::to_value(plan.recipe)
                .ok()
                .and_then(|v| v.as_str().map(str::to_string))
                .unwrap_or_default(),
            file.file_name()
                .map(|f| f.to_string_lossy().into_owned())
                .unwrap_or_default()
        ),
        ..Default::default()
    };
    if plan.recipe.is_none() {
        outcome.error = plan.why_not.clone();
        return outcome;
    }
    if !tulsi_state::is_valid_local_name(&answers.name) {
        outcome.error = format!(
            "\"{}\" cannot be a package name: use lower-case letters, digits and dashes.",
            answers.name
        );
        return outcome;
    }
    let dir = data_dir().join(&answers.name);
    if let Err(e) = std::fs::create_dir_all(&dir) {
        outcome.error = format!("cannot create {}: {e}", dir.display());
        return outcome;
    }
    outcome.draft = dir.join("package.nix").display().to_string();
    let info = DraftInfo {
        name: outcome.name.clone(),
        version: outcome.version.clone(),
        description: outcome.description.clone(),
        unfree: outcome.unfree,
        keep_source: outcome.keep_source,
        origin: outcome.origin.clone(),
        program: answers.program.clone(),
    };
    if let Err(e) = std::fs::write(
        dir.join(DRAFT_INFO),
        serde_json::to_string_pretty(&info).expect("draft info serializes") + "\n",
    ) {
        outcome.error = format!("cannot write {}: {e}", dir.join(DRAFT_INFO).display());
        return outcome;
    }
    progress(&format!(
        "tulsi-recipe: adding {} to the Nix store",
        file.display()
    ));
    let store = store_name(&answers.name, &answers.version, file);
    let hash = match add_to_store(file, &store, &dir) {
        Ok(h) => h,
        Err(e) => {
            outcome.error = e;
            return outcome;
        }
    };
    let source = Source {
        store_name: store,
        hash,
    };

    let mut fixes = Fixes::default();
    let mut out_path = None;
    for attempt in 1..=ATTEMPTS {
        let expr = match expression(plan, answers, &source, &fixes) {
            Ok(e) => e,
            Err(e) => {
                outcome.error = e;
                return outcome;
            }
        };
        outcome.expression = expr.clone();
        let file = dir.join("package.nix");
        if let Err(e) = std::fs::write(&file, &expr) {
            outcome.error = format!("cannot write {}: {e}", file.display());
            return outcome;
        }
        progress(&format!("tulsi-recipe: building (attempt {attempt})"));
        let (built, log) = match nix_build(&file, &answers.name, progress) {
            Ok(r) => r,
            Err(e) => {
                outcome.error = e;
                return outcome;
            }
        };
        outcome.log_tail = log
            .iter()
            .rev()
            .take(40)
            .rev()
            .cloned()
            .collect::<Vec<_>>()
            .join("\n");
        let _ = std::fs::write(dir.join("build.log"), log.join("\n") + "\n");
        if let Some(path) = built {
            out_path = Some(path);
            break;
        }
        // What can be fixed without a person?
        let found = read_log(&log);
        let before = fixes.clone();
        if let Some(got) = found.got_hash {
            if matches!(plan.recipe, Some(Recipe::Cargo | Recipe::Go))
                && fixes.dependency_hash.is_none()
            {
                progress("tulsi-recipe: learned the dependencies' hash");
                fixes.dependency_hash = Some(Some(got));
            }
        }
        if found.vendor_folder && plan.recipe == Some(Recipe::Go) {
            fixes.dependency_hash = Some(None);
        }
        for lib in &found.missing_libraries {
            match package_for_soname(lib) {
                Some(pkg) if !fixes.inputs.contains(&pkg) => {
                    progress(&format!("tulsi-recipe: {lib} comes from {pkg}"));
                    fixes.inputs.insert(pkg);
                }
                Some(_) => {}
                None => {
                    if fixes.ignore_missing.insert(lib.clone()) {
                        progress(&format!(
                            "tulsi-recipe: nothing provides {lib}; leaving it out"
                        ));
                    }
                }
            }
        }
        let mut unknown = Vec::new();
        for dep in &found.missing_dependencies {
            match package_for_dependency(dep) {
                Some(pkg) if !fixes.inputs.contains(&pkg) => {
                    progress(&format!("tulsi-recipe: {dep} comes from {pkg}"));
                    fixes.inputs.insert(pkg);
                }
                Some(_) => {}
                None => unknown.push(dep.clone()),
            }
        }
        if fixes == before {
            outcome.error = if unknown.is_empty() {
                "The build failed in a way the recipe cannot fix by itself.".into()
            } else {
                format!(
                    "The build needs {}, which the recipe does not know where to find.",
                    unknown.join(", ")
                )
            };
            return outcome;
        }
    }
    let Some(out_path) = out_path else {
        outcome.error = format!("The build still failed after {ATTEMPTS} attempts.");
        return outcome;
    };
    for lib in &fixes.ignore_missing {
        outcome.warnings.push(format!(
            "Nothing in TulsiOS provides {lib}; the program may not start, or lack a feature."
        ));
    }
    try_built(outcome, out_path, &answers.program, progress)
}

/// Builds a draft as it is written, after a person edited it: `dir` holds
/// `package.nix` and `recipe.json` (what `build` wrote). Nothing is fixed by itself;
/// the same safety check, build and sandboxed try as `build` apply.
pub fn build_draft(dir: &Path, progress: &mut dyn FnMut(&str)) -> Outcome {
    let mut outcome = Outcome::default();
    let file = dir.join("package.nix");
    outcome.draft = file.display().to_string();
    let info: DraftInfo = match std::fs::read_to_string(dir.join(DRAFT_INFO))
        .map_err(|e| e.to_string())
        .and_then(|t| serde_json::from_str(&t).map_err(|e| e.to_string()))
    {
        Ok(i) => i,
        Err(e) => {
            outcome.error = format!(
                "{} is missing or unreadable ({e}); it says what the package is called.",
                dir.join(DRAFT_INFO).display()
            );
            return outcome;
        }
    };
    outcome.name = info.name.clone();
    outcome.version = info.version.clone();
    outcome.description = info.description.clone();
    outcome.unfree = info.unfree;
    outcome.keep_source = info.keep_source;
    let base = info
        .origin
        .split_once(':')
        .map(|(_, rest)| rest)
        .unwrap_or(&info.origin);
    outcome.origin = format!("edited:{base}");
    if !tulsi_state::is_valid_local_name(&info.name) {
        outcome.error = format!("\"{}\" cannot be a package name.", info.name);
        return outcome;
    }
    let expr = match std::fs::read_to_string(&file) {
        Ok(e) => e,
        Err(e) => {
            outcome.error = format!("cannot read {}: {e}", file.display());
            return outcome;
        }
    };
    outcome.expression = expr.clone();
    // Marked proprietary while editing: its licence is accepted on Install.
    if expr.contains("licenses.unfree") {
        outcome.unfree = true;
    }
    let problems = tulsi_state::check_expression(&expr);
    if !problems.is_empty() {
        outcome.error = format!(
            "TulsiOS cannot install it as written: {}.",
            problems.join("; ")
        );
        return outcome;
    }
    progress("tulsi-recipe: building");
    let (built, log) = match nix_build(&file, &info.name, progress) {
        Ok(r) => r,
        Err(e) => {
            outcome.error = e;
            return outcome;
        }
    };
    outcome.log_tail = log
        .iter()
        .rev()
        .take(40)
        .rev()
        .cloned()
        .collect::<Vec<_>>()
        .join("\n");
    let _ = std::fs::write(dir.join("build.log"), log.join("\n") + "\n");
    let Some(out_path) = built else {
        outcome.error = "The build failed; the end of its log says why.".into();
        return outcome;
    };
    try_built(outcome, out_path, &info.program, progress)
}

/// After a successful build: the package's programs, and its main program tried.
fn try_built(
    mut outcome: Outcome,
    out_path: String,
    program: &str,
    progress: &mut dyn FnMut(&str),
) -> Outcome {
    outcome.out_path = out_path.clone();
    let bin = Path::new(&out_path).join("bin");
    outcome.programs = std::fs::read_dir(&bin)
        .map(|rd| {
            let mut v: Vec<String> = rd
                .filter_map(|e| e.ok())
                .map(|e| e.file_name().to_string_lossy().into_owned())
                .filter(|n| !n.starts_with('.'))
                .collect();
            v.sort();
            v
        })
        .unwrap_or_default();
    if outcome.programs.is_empty() {
        outcome.error = "The package was built, but has no programs.".into();
        return outcome;
    }
    let main = if outcome.programs.iter().any(|p| p == program) {
        program.to_string()
    } else if outcome.programs.contains(&outcome.name) {
        outcome.name.clone()
    } else {
        outcome.programs[0].clone()
    };
    progress(&format!("tulsi-recipe: trying {main}"));
    progress("tulsi-recipe: (in a sandbox: no network, none of your files)");
    let tried = try_program(&bin.join(&main));
    if tried.output.starts_with("not tried") {
        outcome.warnings.push(format!(
            "{main} was not tried: there is no sandbox to run it in safely."
        ));
    } else if !tried.ok {
        outcome.warnings.push(format!(
            "{main} did not start: {}",
            tried.output.lines().next().unwrap_or("")
        ));
    }
    outcome.tried = Some(tried);
    outcome.ok = true;
    outcome
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lines(text: &str) -> Vec<String> {
        text.lines().map(str::to_string).collect()
    }

    #[test]
    fn reads_what_can_be_fixed() {
        let log = lines(
            "auto-patchelf: 2 dependencies could not be satisfied\n\
             error: auto-patchelf could not satisfy dependency libX11.so.6 wanted by /nix/store/x/bin/frob\n\
             error: auto-patchelf could not satisfy dependency libweird.so.3 wanted by /nix/store/x/bin/frob\n\
             Package 'gtk+-3.0', required by 'virtual:world', not found\n\
             Run-time dependency glib-2.0 found: NO (tried pkgconfig)\n\
             meson.build:5:0: ERROR: Dependency \"libcurl\" not found, tried pkgconfig\n\
             Could NOT find ZLIB (missing: ZLIB_LIBRARY)\n\
             specified: sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\n\
                  got:    sha256-BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=",
        );
        let f = read_log(&log);
        assert_eq!(
            f.missing_libraries.into_iter().collect::<Vec<_>>(),
            ["libX11.so.6", "libweird.so.3"]
        );
        assert_eq!(
            f.missing_dependencies.into_iter().collect::<Vec<_>>(),
            ["ZLIB", "gtk+-3.0", "libcurl"]
        );
        assert_eq!(
            f.got_hash.as_deref(),
            Some("sha256-BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=")
        );
    }

    fn draft_dir(name: &str, expr: &str, info: Option<&DraftInfo>) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("tulsi-draft-{}-{name}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("package.nix"), expr).unwrap();
        if let Some(info) = info {
            std::fs::write(dir.join(DRAFT_INFO), serde_json::to_string(info).unwrap()).unwrap();
        }
        dir
    }

    #[test]
    fn draft_info_round_trips() {
        let info = DraftInfo {
            name: "frob".into(),
            version: "1.0".into(),
            unfree: true,
            keep_source: true,
            origin: "recipe:deb frob.deb".into(),
            program: "frob".into(),
            ..Default::default()
        };
        let text = serde_json::to_string(&info).unwrap();
        assert!(text.contains("\"keepSource\":true"));
        assert_eq!(serde_json::from_str::<DraftInfo>(&text).unwrap(), info);
    }

    #[test]
    fn an_edited_draft_is_checked_before_it_is_built() {
        let info = DraftInfo {
            name: "frob".into(),
            version: "1.0".into(),
            origin: "recipe:deb frob.deb".into(),
            ..Default::default()
        };
        let dir = draft_dir(
            "path",
            "{ stdenv }: stdenv.mkDerivation { name = \"x\"; src = ./secret; }",
            Some(&info),
        );
        let o = build_draft(&dir, &mut |_| {});
        assert!(!o.ok);
        assert!(
            o.error.starts_with("TulsiOS cannot install it as written"),
            "{}",
            o.error
        );
        assert_eq!(o.origin, "edited:deb frob.deb");
        assert_eq!(o.name, "frob");

        let dir = draft_dir("noinfo", "{ stdenv }: stdenv.mkDerivation { }", None);
        let o = build_draft(&dir, &mut |_| {});
        assert!(o.error.contains("recipe.json"), "{}", o.error);
    }
}
