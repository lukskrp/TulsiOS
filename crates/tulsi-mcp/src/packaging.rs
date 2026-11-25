//! Packaging tools: an agent turns software from anywhere into a local TulsiOS package
//! (ADR 0013). It fetches and inspects the source, writes a Nix expression, builds it
//! in Nix's sandbox and tries the result; then `propose_local_package` (server.rs) asks
//! the human and hands it to tulsid.
//!
//! Drafts live in `$HOME/packaging/<name>/` (under Starah, the agent's workspace).
//! Builds use the system's pinned nixpkgs at /etc/tulsi/nixpkgs.

use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::time::Duration;

use serde_json::{json, Value};
use tokio::process::Command;

const NIXPKGS: &str = "/etc/tulsi/nixpkgs";
use tulsi_inspect::BSDTAR;
const BUILD_TIMEOUT: Duration = Duration::from_secs(45 * 60);
const RUN_TIMEOUT: Duration = Duration::from_secs(20);
const LOG_LINES: usize = 60;
const MAX_LISTING: usize = 150;

/// Markers that tell how something is built, by file name.
const MARKERS: &[(&str, &str)] = &[
    (
        "configure",
        "autotools (./configure && make): stdenv.mkDerivation",
    ),
    (
        "configure.ac",
        "autotools source: stdenv.mkDerivation + autoreconfHook",
    ),
    ("CMakeLists.txt", "CMake: stdenv.mkDerivation + cmake"),
    (
        "meson.build",
        "Meson: stdenv.mkDerivation + meson ninja pkg-config",
    ),
    (
        "Cargo.toml",
        "Rust: rustPlatform.buildRustPackage (cargoHash)",
    ),
    ("go.mod", "Go: buildGoModule (vendorHash)"),
    (
        "pyproject.toml",
        "Python: python3Packages.buildPythonApplication (pyproject = true)",
    ),
    ("setup.py", "Python: python3Packages.buildPythonApplication"),
    ("package.json", "Node.js: buildNpmPackage (npmDepsHash)"),
    (
        "Makefile",
        "make: stdenv.mkDerivation (check the install target / makeFlags PREFIX=$out)",
    ),
    (
        "debian-binary",
        ".deb package: unpack with dpkg -x, then autoPatchelfHook",
    ),
];

fn workspace() -> PathBuf {
    std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir)
        .join("packaging")
}

fn tail(text: &str, n: usize) -> String {
    let lines: Vec<&str> = text.lines().collect();
    lines[lines.len().saturating_sub(n)..].join("\n")
}

async fn run(cmd: &mut Command, timeout: Duration) -> Result<(bool, String, String), String> {
    cmd.stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);
    let child = cmd.spawn().map_err(|e| format!("cannot start: {e}"))?;
    match tokio::time::timeout(timeout, child.wait_with_output()).await {
        Err(_) => Err(format!("timed out after {} s", timeout.as_secs())),
        Ok(Err(e)) => Err(e.to_string()),
        Ok(Ok(out)) => Ok((
            out.status.success(),
            String::from_utf8_lossy(&out.stdout).into_owned(),
            String::from_utf8_lossy(&out.stderr).into_owned(),
        )),
    }
}

fn nix() -> Command {
    let mut c = Command::new("nix");
    c.args(["--extra-experimental-features", "nix-command"]);
    c
}

/// `fetch_source`: downloads (or takes from the store) a source and describes it.
pub async fn fetch_source(args: &Value) -> Result<(String, Value), String> {
    let (path, hash, origin) = if let Some(url) = args["url"].as_str().filter(|u| !u.is_empty()) {
        if !(url.starts_with("https://") || url.starts_with("http://")) {
            return Err("url must be http(s)".into());
        }
        let (ok, out, err) = run(
            nix().args([
                "store",
                "prefetch-file",
                "--json",
                "--hash-type",
                "sha256",
                url,
            ]),
            Duration::from_secs(15 * 60),
        )
        .await?;
        if !ok {
            return Err(format!("download failed:\n{}", tail(&err, 20)));
        }
        let v: Value = serde_json::from_str(&out).map_err(|e| e.to_string())?;
        (
            v["storePath"].as_str().unwrap_or_default().to_string(),
            v["hash"].as_str().unwrap_or_default().to_string(),
            url.to_string(),
        )
    } else if let Some(p) = args["store_path"]
        .as_str()
        .filter(|p| p.starts_with("/nix/store/"))
    {
        let (ok, out, err) = run(
            nix().args(["hash", "file", "--sri", "--type", "sha256", p]),
            Duration::from_secs(120),
        )
        .await?;
        if !ok {
            return Err(format!("cannot hash {p}: {}", tail(&err, 5)));
        }
        (p.to_string(), out.trim().to_string(), p.to_string())
    } else {
        return Err("give `url` (http/https) or `store_path` (/nix/store/…)".into());
    };

    let file = Path::new(&path);
    let sniffed = tulsi_inspect::sniff(file);
    let kind = sniffed.hint();
    let mut listing = Vec::new();
    if sniffed.listable() {
        if let Ok((true, out, _)) = run(
            Command::new(BSDTAR).arg("-tf").arg(&path),
            Duration::from_secs(60),
        )
        .await
        {
            listing = out.lines().map(str::to_string).collect();
        }
    }
    let mut hints: Vec<&str> = Vec::new();
    for (marker, hint) in MARKERS {
        if listing
            .iter()
            .any(|l| l.trim_end_matches('/').rsplit('/').next() == Some(*marker))
        {
            hints.push(hint);
        }
    }
    let desktop: Vec<&String> = listing.iter().filter(|l| l.ends_with(".desktop")).collect();
    let name = file
        .file_name()
        .map(|n| {
            n.to_string_lossy()
                .split_once('-')
                .map_or(n.to_string_lossy().into_owned(), |(_, rest)| {
                    rest.to_string()
                })
        })
        .unwrap_or_default();
    let mut text = format!(
        "Source: {origin}\nStore path: {path}\nFile name: {name}\nHash: {hash}\nKind: {kind}\n"
    );
    if !hints.is_empty() {
        text.push_str(&format!("Build hints:\n  - {}\n", hints.join("\n  - ")));
    }
    if !desktop.is_empty() {
        text.push_str(&format!(
            "Desktop entries: {}\n",
            desktop
                .iter()
                .map(|s| s.as_str())
                .collect::<Vec<_>>()
                .join(", ")
        ));
    }
    if !listing.is_empty() {
        text.push_str(&format!(
            "Contents ({} entries{}):\n{}\n",
            listing.len(),
            if listing.len() > MAX_LISTING {
                ", first shown"
            } else {
                ""
            },
            listing
                .iter()
                .take(MAX_LISTING)
                .cloned()
                .collect::<Vec<_>>()
                .join("\n")
        ));
    }
    if origin.starts_with("/nix/store/") {
        text.push_str(&format!(
            "Use it as: src = requireFile {{ name = \"{name}\"; hash = \"{hash}\"; message = \"…\"; \
             meta.license = <its licence, e.g. lib.licenses.mit>; }};\n\
             (requireFile counts as unfree unless meta.license says otherwise.)\n"
        ));
    } else {
        text.push_str(&format!(
            "Use it as: src = fetchurl {{ url = \"{origin}\"; hash = \"{hash}\"; }};\n"
        ));
    }
    Ok((
        text,
        json!({ "storePath": path, "hash": hash, "kind": kind, "origin": origin, "hints": hints }),
    ))
}

fn draft_dir(name: &str) -> Result<PathBuf, String> {
    if !tulsi_state::is_valid_local_name(name) {
        return Err(format!(
            "invalid package name {name:?}: lowercase letters, digits and dashes"
        ));
    }
    Ok(workspace().join(name))
}

/// `build_package`: saves the draft expression and builds it in Nix's sandbox.
pub async fn build_package(args: &Value) -> Result<(String, Value), String> {
    let name = args["name"].as_str().ok_or("missing `name`")?;
    let expression = args["expression"].as_str().ok_or("missing `expression`")?;
    let problems = tulsi_state::check_expression(expression);
    if !problems.is_empty() {
        return Err(format!(
            "the expression is not allowed:\n- {}",
            problems.join("\n- ")
        ));
    }
    let dir = draft_dir(name)?;
    std::fs::create_dir_all(&dir).map_err(|e| format!("cannot create {}: {e}", dir.display()))?;
    let file = dir.join("package.nix");
    std::fs::write(&file, expression).map_err(|e| e.to_string())?;
    let expr = format!(
        "(import {NIXPKGS} {{ }}).callPackage {} {{ }}",
        file.display()
    );
    let (ok, out, err) = run(
        Command::new("nix-build").args(["--no-out-link", "--expr", &expr]),
        BUILD_TIMEOUT,
    )
    .await?;
    if !ok {
        let mut text = format!("Build failed. Last lines:\n{}", tail(&err, LOG_LINES));
        // Hash iteration: `lib.fakeHash` first, then the hash Nix reports.
        if let Some(got) = err
            .lines()
            .find_map(|l| l.trim().strip_prefix("got:").map(|h| h.trim().to_string()))
        {
            text.push_str(&format!(
                "\n\nA fixed-output hash did not match: use \"{got}\" where the build \
                 expected a hash (src hash, cargoHash, vendorHash or npmDepsHash)."
            ));
        }
        return Err(text);
    }
    let out_path = out.lines().last().unwrap_or_default().trim().to_string();
    std::fs::write(dir.join("result"), &out_path).ok();
    let bins: Vec<String> = std::fs::read_dir(Path::new(&out_path).join("bin"))
        .map(|rd| {
            rd.filter_map(|e| e.ok())
                .map(|e| e.file_name().to_string_lossy().into_owned())
                .collect()
        })
        .unwrap_or_default();
    Ok((
        format!(
            "Built {out_path}\nPrograms in bin/: {}\nNext: try_package to run it, then \
             propose_local_package.",
            if bins.is_empty() {
                "(none)".to_string()
            } else {
                bins.join(", ")
            }
        ),
        json!({ "outPath": out_path, "programs": bins }),
    ))
}

/// `try_package`: runs a built program briefly, in a throwaway home.
pub async fn try_package(args: &Value) -> Result<(String, Value), String> {
    let name = args["name"].as_str().ok_or("missing `name`")?;
    let dir = draft_dir(name)?;
    let out_path = std::fs::read_to_string(dir.join("result"))
        .map_err(|_| format!("build {name} first (build_package)"))?;
    let bin = Path::new(out_path.trim()).join("bin");
    let program = match args["program"].as_str() {
        Some(p) if !p.contains('/') => bin.join(p),
        Some(_) => return Err("`program` is a file name in the package's bin/".into()),
        None => std::fs::read_dir(&bin)
            .ok()
            .and_then(|mut rd| rd.next())
            .and_then(|e| e.ok())
            .map(|e| e.path())
            .ok_or("the package has no programs in bin/")?,
    };
    let argv: Vec<String> = args["args"]
        .as_array()
        .map(|a| {
            a.iter()
                .filter_map(|v| v.as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_else(|| vec!["--version".into()]);
    let home = dir.join("try-home");
    let _ = std::fs::remove_dir_all(&home);
    std::fs::create_dir_all(&home).map_err(|e| e.to_string())?;
    let (ok, out, err) = run(
        Command::new(&program)
            .args(&argv)
            .env("HOME", &home)
            .env("XDG_CONFIG_HOME", home.join(".config"))
            .env_remove("DISPLAY")
            .env_remove("WAYLAND_DISPLAY"),
        RUN_TIMEOUT,
    )
    .await?;
    let shown = |s: &str| s.chars().take(3000).collect::<String>();
    Ok((
        format!(
            "{} {} → {}\nstdout:\n{}\nstderr:\n{}",
            program.display(),
            argv.join(" "),
            if ok { "exit 0" } else { "failed" },
            shown(&out),
            shown(&err)
        ),
        json!({ "ok": ok, "stdout": shown(&out), "stderr": shown(&err) }),
    ))
}
