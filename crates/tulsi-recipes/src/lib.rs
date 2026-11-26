//! Recipes (ADR 0018): downloaded software becomes a local TulsiOS package from
//! tested templates, with no model. `plan` says which recipe fits a file (from
//! `tulsi_inspect`) and what to ask; `expression` writes the package from the
//! answers; `build` (build.rs) builds it, fixing what it can by itself (missing
//! libraries, dependency hashes), and tries the result.
//!
//! Recipes: AppImages; single prebuilt programs; prebuilt programs in .deb, .rpm,
//! tar and zip files; and source code built with CMake, Meson, autotools, make,
//! Cargo or Go. Anything else is for the Assistant.

use std::collections::BTreeSet;
use std::path::Path;

use tulsi_inspect::{Inspection, Kind};

mod build;
pub use build::{build, build_draft, DraftInfo, Outcome, Tried, DRAFT_INFO};

/// Shared libraries -> the package that has them (data/sonames.json).
const SONAMES: &str = include_str!("../../../data/sonames.json");
/// Build-time dependency names -> packages (data/pkg-config-names.json).
const PKG_CONFIG_NAMES: &str = include_str!("../../../data/pkg-config-names.json");

/// Which template packages a file.
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Recipe {
    AppImage,
    /// One prebuilt program file.
    Binary,
    /// Prebuilt programs in a .deb.
    Deb,
    /// Prebuilt programs in an .rpm.
    Rpm,
    /// Prebuilt programs in a tar or zip archive.
    Archive,
    Cmake,
    Meson,
    Autotools,
    Autoreconf,
    Make,
    Cargo,
    Go,
}

impl Recipe {
    pub fn title(self) -> &'static str {
        match self {
            Recipe::AppImage => "AppImage",
            Recipe::Binary => "Prebuilt program",
            Recipe::Deb => "Prebuilt programs from a .deb package",
            Recipe::Rpm => "Prebuilt programs from an .rpm package",
            Recipe::Archive => "Prebuilt programs from an archive",
            Recipe::Cmake => "Source code built with CMake",
            Recipe::Meson => "Source code built with Meson",
            Recipe::Autotools => "Source code built with ./configure and make",
            Recipe::Autoreconf => "Source code built with autotools",
            Recipe::Make => "Source code built with make",
            Recipe::Cargo => "Rust source code (Cargo)",
            Recipe::Go => "Go source code",
        }
    }

    pub fn is_source(self) -> bool {
        matches!(
            self,
            Recipe::Cmake
                | Recipe::Meson
                | Recipe::Autotools
                | Recipe::Autoreconf
                | Recipe::Make
                | Recipe::Cargo
                | Recipe::Go
        )
    }

    fn of_build_system(system: &str) -> Option<Recipe> {
        Some(match system {
            "cmake" => Recipe::Cmake,
            "meson" => Recipe::Meson,
            "autotools" => Recipe::Autotools,
            "autoreconf" => Recipe::Autoreconf,
            "make" => Recipe::Make,
            "cargo" => Recipe::Cargo,
            "go" => Recipe::Go,
            _ => return None,
        })
    }
}

/// What a recipe would do with a file, and the suggested answers.
#[derive(Debug, Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Plan {
    pub recipe: Option<Recipe>,
    pub title: String,
    /// Why no recipe fits, for people.
    pub why_not: String,
    /// A valid local package name (lower case, digits, dashes).
    pub name: String,
    pub version: String,
    pub description: String,
    pub homepage: String,
    /// Programs to choose the main one from (prebuilt recipes).
    pub programs: Vec<String>,
    /// The suggested main program.
    pub program: String,
    /// "free", "unfree" or "" (unknown: ask).
    pub license: String,
    /// The licence the package declares, if any.
    pub license_text: String,
    /// Suggest adding it to the applications menu.
    pub menu: bool,
    pub inspection: Inspection,
}

/// What the person chose.
#[derive(Debug, Clone, Default, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", default)]
pub struct Answers {
    pub name: String,
    pub version: String,
    pub description: String,
    pub program: String,
    pub unfree: bool,
    pub menu: bool,
    /// Keep the downloaded file as part of the system (state.json `keepSources`).
    pub keep_source: bool,
}

/// The downloaded file, in the Nix store (see `store_name`).
#[derive(Debug, Clone, Default)]
pub struct Source {
    pub store_name: String,
    pub hash: String,
}

/// What `build` learned from failed attempts.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Fixes {
    /// Extra build inputs (attribute paths).
    pub inputs: BTreeSet<String>,
    /// Libraries nothing provides; the program may still work without them.
    pub ignore_missing: BTreeSet<String>,
    /// cargoHash / vendorHash once Nix reported it; `Some(None)` = `vendorHash = null`.
    pub dependency_hash: Option<Option<String>>,
}

/// A valid local package name from anything: `My App 2` -> `my-app-2`.
pub fn local_name(s: &str) -> String {
    let mut out = String::new();
    for c in s.chars() {
        if c.is_ascii_alphanumeric() {
            out.push(c.to_ascii_lowercase());
        } else if !out.ends_with('-') && !out.is_empty() {
            out.push('-');
        }
    }
    let mut out = out.trim_matches('-').to_string();
    if !out.starts_with(|c: char| c.is_ascii_lowercase()) {
        out.insert_str(0, "app-");
    }
    out.truncate(64);
    out.trim_end_matches('-').to_string()
}

/// The source's name in the store: `<name>-<version>-<file>`, so that Nix reads the
/// package's name from it (`lib.getName`); an accepted licence then covers the
/// downloaded file too.
pub fn store_name(name: &str, version: &str, file: &Path) -> String {
    let version = if version.starts_with(|c: char| c.is_ascii_digit()) {
        version
    } else {
        "0"
    };
    let base = file
        .file_name()
        .map(|f| f.to_string_lossy().into_owned())
        .unwrap_or_default();
    let mut clean: String = base
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || "+-._?=".contains(c) {
                c
            } else {
                '_'
            }
        })
        .collect();
    clean = clean.trim_start_matches('.').to_string();
    let mut s = format!("{name}-{version}-{clean}");
    s.truncate(200);
    s
}

/// Words in declared licences that mean free software.
const FREE_LICENSES: &[&str] = &[
    "mit",
    "gpl",
    "bsd",
    "apache",
    "mpl",
    "isc",
    "zlib",
    "artistic",
    "cc0",
    "unlicense",
    "eupl",
    "ofl",
    "boost",
    "psf",
    "python",
];

fn license_kind(text: &str) -> &'static str {
    let lower = text.to_lowercase();
    if lower.contains("proprietary") || lower.contains("commercial") {
        "unfree"
    } else if !lower.is_empty() && FREE_LICENSES.iter().any(|w| lower.contains(w)) {
        "free"
    } else {
        ""
    }
}

/// Which recipe fits `insp`, with suggested answers.
pub fn plan(insp: &Inspection) -> Plan {
    let kind = insp.kind.unwrap_or(Kind::Unknown);
    let mut why_not = String::new();
    let recipe = match kind {
        Kind::AppImage => Some(Recipe::AppImage),
        Kind::Binary => Some(Recipe::Binary),
        Kind::Deb | Kind::Rpm if insp.programs.is_empty() => {
            why_not = "There are no programs in it (it may be a library or a plug-in).".into();
            None
        }
        Kind::Deb => Some(Recipe::Deb),
        Kind::Rpm => Some(Recipe::Rpm),
        Kind::Archive => match Recipe::of_build_system(&insp.build_system) {
            Some(r) => Some(r),
            None if insp.build_system == "python" => {
                why_not = "Python projects need their dependencies worked out, which a \
                           recipe cannot do yet."
                    .into();
                None
            }
            None if !insp.programs.is_empty() => Some(Recipe::Archive),
            None => {
                why_not = "It has neither ready-made programs nor build files a recipe \
                           knows."
                    .into();
                None
            }
        },
        Kind::Installer => {
            why_not = "Installer scripts can do anything; someone has to read this one \
                       first."
                .into();
            None
        }
        Kind::FlatpakRef => {
            why_not = "TulsiOS installs Nix packages, not Flatpaks.".into();
            None
        }
        Kind::Windows => {
            why_not = "This is a Windows program: run it with Bottles rather than \
                       packaging it."
                .into();
            None
        }
        Kind::Unknown => {
            why_not = "TulsiOS does not recognise this kind of file.".into();
            None
        }
    };
    let name = local_name(&insp.name);
    let program = insp
        .programs
        .iter()
        .find(|p| local_name(p) == name)
        .or_else(|| insp.programs.first())
        .cloned()
        .unwrap_or_default();
    let menu = matches!(recipe, Some(Recipe::AppImage))
        || !insp.desktop_files.is_empty()
        || (matches!(recipe, Some(Recipe::Archive)) && !insp.icons.is_empty());
    Plan {
        title: recipe.map(Recipe::title).unwrap_or_default().to_string(),
        recipe,
        why_not,
        version: if insp.version.is_empty() {
            "0".into()
        } else {
            insp.version.clone()
        },
        description: insp.description.clone(),
        homepage: insp.homepage.clone(),
        programs: insp.programs.clone(),
        program,
        license: license_kind(&insp.license).into(),
        license_text: insp.license.clone(),
        menu,
        name,
        inspection: insp.clone(),
    }
}

/// The shared-library table: `libX11.so.6` -> `xorg.libX11`.
pub fn package_for_soname(soname: &str) -> Option<String> {
    let table: serde_json::Map<String, serde_json::Value> =
        serde_json::from_str(SONAMES).expect("data/sonames.json is valid");
    let key = match soname.find(".so") {
        Some(i) => &soname[..i + 3],
        None => soname,
    };
    table.get(key)?.as_str().map(str::to_string)
}

/// The build-dependency table: `gtk+-3.0` -> `gtk3`.
pub fn package_for_dependency(name: &str) -> Option<String> {
    let table: serde_json::Map<String, serde_json::Value> =
        serde_json::from_str(PKG_CONFIG_NAMES).expect("data/pkg-config-names.json is valid");
    table
        .get(&name.to_lowercase())?
        .as_str()
        .map(str::to_string)
}

// ------------------------------------------------------------------ templates

/// A Nix double-quoted string.
fn q(s: &str) -> String {
    let mut out = String::from('"');
    let mut chars = s.chars().peekable();
    while let Some(c) = chars.next() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '$' if chars.peek() == Some(&'{') => out.push_str("\\$"),
            '\n' | '\r' => out.push(' '),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// A relative path inside the package, for shell code in an indented string: only
/// plain characters (no quotes, `$`, backslashes or `..`), single-quoted.
fn shell_path(p: &str) -> Option<String> {
    let ok = !p.is_empty()
        && !p.starts_with('/')
        && !p.split('/').any(|s| s == "..")
        && p.chars()
            .all(|c| c.is_ascii_alphanumeric() || " ._+-/@,".contains(c));
    ok.then(|| format!("'{p}'"))
}

/// The function arguments for a set of attribute paths (`xorg.libX11` -> `xorg`).
fn args_of<'a>(fixed: &[&'a str], inputs: impl IntoIterator<Item = &'a String>) -> String {
    let mut args: Vec<String> = fixed.iter().map(|s| s.to_string()).collect();
    for i in inputs {
        let head = i.split('.').next().unwrap_or(i).to_string();
        if !args.contains(&head) {
            args.push(head);
        }
    }
    format!("{{ {} }}:", args.join(", "))
}

fn list(items: &BTreeSet<String>) -> String {
    if items.is_empty() {
        "[ ]".into()
    } else {
        format!(
            "[ {} ]",
            items.iter().cloned().collect::<Vec<_>>().join(" ")
        )
    }
}

fn quoted_list(items: &BTreeSet<String>) -> String {
    if items.is_empty() {
        "[ ]".into()
    } else {
        format!(
            "[ {} ]",
            items.iter().map(|i| q(i)).collect::<Vec<_>>().join(" ")
        )
    }
}

/// Runtime libraries Electron and Chromium load without linking them.
const ELECTRON_RUNTIME: &[&str] = &["systemd", "libGL", "libnotify", "libpulseaudio"];

/// Writes the package for `plan`, `answers` and the stored `source`, with what
/// earlier attempts learned. Errors when the download's paths cannot be used safely.
pub fn expression(
    plan: &Plan,
    answers: &Answers,
    source: &Source,
    fixes: &Fixes,
) -> Result<String, String> {
    let recipe = plan.recipe.ok_or("no recipe fits this file")?;
    let name = &answers.name;
    if !tulsi_state::is_valid_local_name(name) {
        return Err(format!("invalid package name {name:?}"));
    }
    let license = if answers.unfree {
        "lib.licenses.unfree"
    } else {
        "lib.licenses.free"
    };
    let src = format!(
        "requireFile {{\n    name = {};\n    hash = {};\n    message = {};\n    meta.license = {license};\n  }}",
        q(&source.store_name),
        q(&source.hash),
        q("Added to the Nix store by TulsiOS (tulsi-adopt)."),
    );
    let program = if answers.program.is_empty() {
        name.clone()
    } else {
        answers.program.clone()
    };
    let mut meta = format!(
        "{{\n    description = {};\n    license = {license};\n",
        q(if answers.description.is_empty() {
            &plan.description
        } else {
            &answers.description
        })
    );
    if plan.homepage.starts_with("http") {
        meta.push_str(&format!("    homepage = {};\n", q(&plan.homepage)));
    }
    if !recipe.is_source() || !answers.program.is_empty() {
        meta.push_str(&format!("    mainProgram = {};\n", q(&program)));
    }
    meta.push_str("  }");
    let header = format!(
        "# Made by a TulsiOS recipe ({}) from a downloaded file (ADR 0018).\n",
        recipe.title()
    );
    let insp = &plan.inspection;
    let mut inputs = fixes.inputs.clone();
    let mut runtime: BTreeSet<String> = BTreeSet::new();
    if insp.electron {
        runtime.extend(ELECTRON_RUNTIME.iter().map(|s| s.to_string()));
    }
    let ignore = quoted_list(&fixes.ignore_missing);
    let pv = format!(
        "  pname = {};\n  version = {};\n  src = {src};\n",
        q(name),
        q(&answers.version)
    );

    let body = match recipe {
        Recipe::AppImage => {
            let menu = if answers.menu {
                "\n    for d in ${contents}/*.desktop; do\n      install -Dm444 \"$d\" $out/share/applications/${pname}.desktop\n      sed -i -E 's|^Exec=[^ ]*|Exec=${pname}|' $out/share/applications/${pname}.desktop\n      break\n    done\n    if [ -d ${contents}/usr/share/icons ]; then\n      cp -r ${contents}/usr/share/icons $out/share/\n    fi\n    for i in ${contents}/*.png ${contents}/*.svg; do\n      if [ -e \"$i\" ]; then install -Dm444 \"$i\" $out/share/pixmaps/$(basename \"$i\"); fi\n    done"
            } else {
                ""
            };
            format!(
                "{header}{{ lib, appimageTools, requireFile }}:\nlet\n  pname = {};\n  version = {};\n  src = {src};\n  contents = appimageTools.extract {{ inherit pname version src; }};\nin\nappimageTools.wrapType2 {{\n  inherit pname version src;\n  extraInstallCommands = ''{menu}\n  '';\n  meta = {meta};\n}}\n",
                q(name),
                q(&answers.version),
            )
        }
        Recipe::Binary => {
            let target = shell_path(&program).ok_or("the program's name has unusual characters")?;
            format!(
                "{header}{}\nstdenv.mkDerivation {{\n{pv}  dontUnpack = true;\n  nativeBuildInputs = [ autoPatchelfHook ];\n  buildInputs = {};\n  autoPatchelfIgnoreMissingDeps = {ignore};\n  installPhase = ''\n    runHook preInstall\n    install -Dm755 $src $out/bin/{target}\n    runHook postInstall\n  '';\n  meta = {meta};\n}}\n",
                args_of(&["lib", "stdenv", "requireFile", "autoPatchelfHook"], &inputs),
                list(&inputs),
            )
        }
        Recipe::Deb | Recipe::Rpm => {
            let (unpacker, unpack) = if recipe == Recipe::Deb {
                ("dpkg", "${dpkg}/bin/dpkg-deb -x $src source")
            } else {
                ("libarchive", "${libarchive}/bin/bsdtar -xf $src -C source")
            };
            let menu = if answers.menu {
                "    for f in $out/share/applications/*.desktop; do\n      if [ -e \"$f\" ]; then\n        substituteInPlace \"$f\" --replace-quiet /usr/bin/ \"\" --replace-quiet /opt/ \"$out/opt/\"\n      fi\n    done\n"
            } else {
                "    rm -rf $out/share/applications\n"
            };
            let sandbox = if insp.electron {
                "    # Electron: without a setuid helper, Chromium's own sandbox uses namespaces.\n    find $out -name chrome-sandbox -delete\n"
            } else {
                ""
            };
            let mut all: BTreeSet<String> = inputs.clone();
            all.extend(runtime.iter().cloned());
            format!(
                "{header}{}\nstdenv.mkDerivation {{\n{pv}  nativeBuildInputs = [ autoPatchelfHook ];\n  buildInputs = {};\n  runtimeDependencies = {};\n  autoPatchelfIgnoreMissingDeps = {ignore};\n  unpackPhase = ''\n    runHook preUnpack\n    mkdir source\n    {unpack}\n    cd source\n    runHook postUnpack\n  '';\n  dontConfigure = true;\n  dontBuild = true;\n  installPhase = ''\n    runHook preInstall\n    mkdir -p $out\n    if [ -d usr ]; then cp -a usr/. $out/; fi\n    if [ -d opt ]; then cp -a opt $out/; fi\n    # Links into /usr or /opt now point into the package.\n    find $out -type l | while read -r link; do\n      target=$(readlink \"$link\")\n      case \"$target\" in\n        /usr/*) ln -sfn \"$out/''${{target#/usr/}}\" \"$link\" ;;\n        /opt/*) ln -sfn \"$out$target\" \"$link\" ;;\n      esac\n    done\n{menu}{sandbox}    runHook postInstall\n  '';\n  meta = {meta};\n}}\n",
                args_of(&["lib", "stdenv", "requireFile", "autoPatchelfHook", unpacker], &all),
                list(&inputs),
                list(&runtime),
            )
        }
        Recipe::Archive => {
            let root = if insp.root.is_empty() {
                "'.'".to_string()
            } else {
                shell_path(&insp.root).ok_or("the archive's folder name has unusual characters")?
            };
            let mut wrappers = String::new();
            for path in &insp.program_paths {
                let inside = path
                    .strip_prefix(&format!("{}/", insp.root))
                    .unwrap_or(path);
                let file = inside.rsplit('/').next().unwrap_or(inside);
                let (Some(from), Some(to)) = (shell_path(inside), shell_path(file)) else {
                    continue;
                };
                wrappers.push_str(&format!(
                    "    makeWrapper $out/share/${{pname}}/{from} $out/bin/{to}\n"
                ));
            }
            let icon = plan.inspection.icons.iter().find_map(|i| {
                let inside = i.strip_prefix(&format!("{}/", insp.root)).unwrap_or(i);
                shell_path(inside).map(|p| (p, i.to_lowercase().ends_with(".svg")))
            });
            let mut extra_native = String::new();
            let mut desktop = String::new();
            let mut icon_install = String::new();
            let mut fixed = vec![
                "lib",
                "stdenv",
                "requireFile",
                "autoPatchelfHook",
                "makeWrapper",
                "libarchive",
            ];
            if answers.menu {
                fixed.push("makeDesktopItem");
                fixed.push("copyDesktopItems");
                extra_native.push_str(" copyDesktopItems");
                let icon_line = match &icon {
                    Some((path, svg)) => {
                        let dest = if *svg {
                            "$out/share/icons/hicolor/scalable/apps/${pname}.svg"
                        } else {
                            "$out/share/icons/hicolor/256x256/apps/${pname}.png"
                        };
                        icon_install = format!("    install -Dm444 {path} {dest}\n");
                        "      icon = pname;\n"
                    }
                    None => "",
                };
                desktop = format!(
                    "  desktopItems = [\n    (makeDesktopItem {{\n      name = pname;\n      desktopName = {};\n      exec = {};\n{icon_line}      comment = {};\n      categories = [ \"Utility\" ];\n    }})\n  ];\n",
                    q(&plan.inspection.name),
                    q(&program),
                    q(&plan.description),
                );
            }
            let sandbox = if insp.electron {
                "    find $out -name chrome-sandbox -delete\n"
            } else {
                ""
            };
            let mut all: BTreeSet<String> = inputs.clone();
            all.extend(runtime.iter().cloned());
            format!(
                "{header}{}\nlet\n  pname = {};\nin\nstdenv.mkDerivation {{\n  inherit pname;\n  version = {};\n  src = {src};\n  nativeBuildInputs = [ autoPatchelfHook makeWrapper{extra_native} ];\n  buildInputs = {};\n  runtimeDependencies = {};\n  autoPatchelfIgnoreMissingDeps = {ignore};\n  unpackPhase = ''\n    runHook preUnpack\n    mkdir source\n    ${{libarchive}}/bin/bsdtar -xf $src -C source\n    cd source\n    runHook postUnpack\n  '';\n  dontConfigure = true;\n  dontBuild = true;\n{desktop}  installPhase = ''\n    runHook preInstall\n    mkdir -p $out/share/${{pname}} $out/bin\n    cp -a {root}/. $out/share/${{pname}}/\n    cd {root}\n{wrappers}{icon_install}{sandbox}    runHook postInstall\n  '';\n  meta = {meta};\n}}\n",
                args_of(&fixed, &all),
                q(name),
                q(&answers.version),
                list(&inputs),
                list(&runtime),
            )
        }
        Recipe::Cargo | Recipe::Go => {
            let hash = match &fixes.dependency_hash {
                None => "lib.fakeHash".to_string(),
                Some(None) => "null".to_string(),
                Some(Some(h)) => q(h),
            };
            let (builder, field) = if recipe == Recipe::Cargo {
                ("rustPlatform.buildRustPackage", "cargoHash")
            } else {
                ("buildGoModule", "vendorHash")
            };
            let head = builder.split('.').next().unwrap_or(builder);
            inputs.remove("pkg-config");
            format!(
                "{header}{}\n{builder} {{\n{pv}{}  {field} = {hash};\n  nativeBuildInputs = [ pkg-config ];\n  buildInputs = {};\n  doCheck = false;\n  meta = {meta};\n}}\n",
                args_of(&["lib", head, "requireFile", "pkg-config"], &inputs),
                source_root(insp),
                list(&inputs),
            )
        }
        Recipe::Cmake | Recipe::Meson | Recipe::Autotools | Recipe::Autoreconf | Recipe::Make => {
            let tools: &[&str] = match recipe {
                Recipe::Cmake => &["cmake", "pkg-config"],
                Recipe::Meson => &["meson", "ninja", "pkg-config"],
                Recipe::Autoreconf => &["autoreconfHook", "pkg-config"],
                _ => &["pkg-config"],
            };
            let mut fixed = vec!["lib", "stdenv", "requireFile"];
            fixed.extend(tools);
            let is_zip = insp.kind.is_some() && source.store_name.to_lowercase().ends_with(".zip");
            let mut native: Vec<&str> = tools.to_vec();
            if is_zip {
                fixed.push("unzip");
                native.push("unzip");
            }
            for t in tools {
                inputs.remove(*t);
            }
            let make = if recipe == Recipe::Make {
                "  dontConfigure = true;\n  makeFlags = [ \"PREFIX=${placeholder \"out\"}\" ];\n"
            } else {
                ""
            };
            format!(
                "{header}{}\nstdenv.mkDerivation {{\n{pv}{}  nativeBuildInputs = [ {} ];\n  buildInputs = {};\n{make}  meta = {meta};\n}}\n",
                args_of(&fixed, &inputs),
                source_root(insp),
                native.join(" "),
                list(&inputs),
            )
        }
    };
    let problems = tulsi_state::check_expression(&body);
    if problems.is_empty() {
        Ok(body)
    } else {
        Err(format!(
            "the recipe's package was refused: {}",
            problems.join("; ")
        ))
    }
}

/// `sourceRoot = ".";` for archives without a single top-level directory.
fn source_root(insp: &Inspection) -> &'static str {
    if insp.root.is_empty() {
        "  sourceRoot = \".\";\n"
    } else {
        ""
    }
}

#[cfg(test)]
mod tests;
