//! What a downloaded file is (ADR 0018): its kind from its first bytes, and for
//! packages and archives the name, version and description they carry and the
//! programs inside. `tulsi-adopt` uses this (through `tulsi inspect`) to find the
//! matching TulsiOS package; tulsi-mcp's `fetch_source` to describe a source.
//!
//! Archives and .deb files are read with bsdtar; .rpm headers are parsed here.

use std::io::{Read, Seek, SeekFrom};
use std::path::Path;
use std::process::{Command, Stdio};

mod rpm;

/// bsdtar from the Nix build (nix/packages/tulsi-tools.nix), else the one on PATH.
pub const BSDTAR: &str = match option_env!("TULSI_BSDTAR") {
    Some(path) => path,
    None => "bsdtar",
};

/// Most programs listed for one file.
const MAX_PROGRAMS: usize = 40;

/// What a file is, from its first bytes (and, for .deb, its name).
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Kind {
    Deb,
    Rpm,
    AppImage,
    /// A prebuilt program (ELF).
    Binary,
    /// zip or compressed tar.
    Archive,
    /// A shell script or self-extracting installer.
    Installer,
    /// A Flatpak application reference (.flatpakref).
    FlatpakRef,
    Unknown,
}

impl Kind {
    /// How a source of this kind is usually packaged (for tulsi-mcp's agent).
    pub fn hint(self) -> &'static str {
        match self {
            Kind::AppImage => "AppImage (use appimageTools.wrapType2)",
            Kind::Binary => "ELF executable (prebuilt binary: autoPatchelfHook)",
            Kind::Deb => ".deb package",
            Kind::Rpm => ".rpm package (unpack with rpmextract / rpm2cpio)",
            Kind::Archive => {
                "compressed tar archive or zip archive (fetchzip, or unzip in nativeBuildInputs)"
            }
            Kind::Installer => "script / self-extracting installer (read it before packaging)",
            Kind::FlatpakRef => "Flatpak reference (TulsiOS installs Nix packages, not Flatpaks)",
            Kind::Unknown => "unknown file type",
        }
    }

    /// Whether bsdtar can list the file's contents.
    pub fn listable(self) -> bool {
        matches!(self, Kind::Deb | Kind::Rpm | Kind::Archive)
    }
}

/// What `inspect` found out about a file.
#[derive(Debug, Clone, Default, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Inspection {
    pub kind: Option<Kind>,
    /// The package's own name (.deb `Package`, .rpm `Name`, Flatpak app), else one
    /// guessed from the file name.
    pub name: String,
    pub version: String,
    pub description: String,
    pub homepage: String,
    /// Other names the package says it provides (.deb `Provides`, .rpm provides).
    pub provides: Vec<String>,
    /// Programs inside: what lands in a `bin` directory, or the executables of an
    /// archive's top level.
    pub programs: Vec<String>,
    /// Where each of `programs` is inside the package (same order), e.g.
    /// `usr/bin/frob`, `opt/Frob/frob`, `frob-1.0/frob`.
    pub program_paths: Vec<String>,
    /// Desktop entries inside (`usr/share/applications/frob.desktop`).
    pub desktop_files: Vec<String>,
    /// Icons inside (PNG or SVG in `share/icons`, `share/pixmaps`, or near the top).
    pub icons: Vec<String>,
    /// How a source archive is built: cargo, go, meson, cmake, autotools,
    /// autoreconf, make or python; empty for prebuilt software.
    pub build_system: String,
    /// The single top-level directory of an archive (`frob-1.0`), if there is one.
    pub root: String,
    /// The licence the package declares (.rpm `License`), e.g. `MIT`, `GPL-3.0-or-later`.
    pub license: String,
    /// Electron or Chromium-based: these load some libraries at run time.
    pub electron: bool,
}

/// The kind of the file at `path`.
pub fn sniff(path: &Path) -> Kind {
    let mut head = [0u8; 64];
    let n = std::fs::File::open(path)
        .and_then(|mut f| f.read(&mut head))
        .unwrap_or(0);
    kind_of(&head[..n], &path.to_string_lossy().to_lowercase())
}

fn kind_of(head: &[u8], lower_name: &str) -> Kind {
    if head.starts_with(b"\x7fELF") {
        if head.len() > 10 && &head[8..11] == b"AI\x02" {
            Kind::AppImage
        } else {
            Kind::Binary
        }
    } else if head.starts_with(b"!<arch>\ndebian") || lower_name.ends_with(".deb") {
        Kind::Deb
    } else if head.starts_with(&[0xed, 0xab, 0xee, 0xdb]) {
        Kind::Rpm
    } else if head.starts_with(b"PK")
        || head.starts_with(&[0x1f, 0x8b])
        || head.starts_with(&[0xfd, b'7', b'z', b'X', b'Z'])
        || head.starts_with(b"BZh")
        || head.starts_with(&[0x28, 0xb5, 0x2f, 0xfd])
    {
        Kind::Archive
    } else if head.starts_with(b"[Flatpak Ref]") {
        Kind::FlatpakRef
    } else if head.starts_with(b"#!") {
        Kind::Installer
    } else {
        Kind::Unknown
    }
}

/// Everything that can be learned about `path` without unpacking it to disk.
pub fn inspect(path: &Path) -> Inspection {
    let kind = sniff(path);
    let mut out = Inspection {
        kind: Some(kind),
        ..Default::default()
    };
    match kind {
        Kind::Deb => inspect_deb(path, &mut out),
        Kind::Rpm => {
            if let Ok(h) = rpm::read_header(path) {
                out.name = h.name;
                out.version = h.version;
                out.description = h.summary;
                out.homepage = h.url;
                out.provides = h.provides;
                out.license = h.license;
            }
            if let Some(listing) = bsdtar_list(&[path.as_os_str()]) {
                contents(&listing, false).fill(&mut out);
            }
        }
        Kind::Archive => {
            if let Some(listing) = bsdtar_list(&[path.as_os_str()]) {
                contents(&listing, true).fill(&mut out);
            }
        }
        Kind::Binary => {
            if let Some(name) = path.file_name() {
                out.programs = vec![name.to_string_lossy().into_owned()];
            }
        }
        Kind::FlatpakRef => {
            if let Ok(text) = std::fs::read_to_string(path) {
                let (app, title) = parse_flatpakref(&text);
                out.name = app;
                out.description = title;
            }
        }
        Kind::AppImage | Kind::Installer | Kind::Unknown => {}
    }
    if out.name.is_empty() {
        out.name = name_from_file(&path.to_string_lossy());
    }
    if out.version.is_empty() {
        out.version = version_from_file(&path.to_string_lossy());
    }
    out.provides.retain(|p| p != &out.name);
    out
}

// ------------------------------------------------------------------------ .deb

fn inspect_deb(path: &Path, out: &mut Inspection) {
    // control.tar.* inside the ar archive, then ./control inside that.
    if let Some(control) = bsdtar_pipe(path, "control.tar*", &["-xOf", "-", "*control"]) {
        let fields = parse_control(&String::from_utf8_lossy(&control));
        let get = |k: &str| {
            fields
                .iter()
                .find(|(key, _)| key.eq_ignore_ascii_case(k))
                .map(|(_, v)| v.clone())
                .unwrap_or_default()
        };
        out.name = get("Package");
        out.version = get("Version");
        out.description = get("Description").lines().next().unwrap_or("").to_string();
        out.homepage = get("Homepage");
        out.provides = split_relations(&get("Provides"));
    }
    if let Some(data) = bsdtar_pipe(path, "data.tar*", &["-tvf", "-"]) {
        contents(&String::from_utf8_lossy(&data), false).fill(out);
    }
}

/// Fields of a Debian control file, continuation lines joined with newlines.
pub fn parse_control(text: &str) -> Vec<(String, String)> {
    let mut fields: Vec<(String, String)> = Vec::new();
    for line in text.lines() {
        if line.starts_with(' ') || line.starts_with('\t') {
            if let Some((_, v)) = fields.last_mut() {
                v.push('\n');
                v.push_str(line.trim());
            }
        } else if let Some((k, v)) = line.split_once(':') {
            fields.push((k.trim().to_string(), v.trim().to_string()));
        }
    }
    fields
}

/// `foo (= 1.0), bar | baz` -> [foo, bar, baz].
fn split_relations(value: &str) -> Vec<String> {
    value
        .split([',', '|'])
        .map(|p| p.split('(').next().unwrap_or("").trim().to_string())
        .filter(|p| !p.is_empty())
        .collect()
}

// ------------------------------------------------------------------ flatpakref

/// The application id's last part (`org.videolan.VLC` -> `vlc`) and the title.
pub fn parse_flatpakref(text: &str) -> (String, String) {
    let mut app = String::new();
    let mut title = String::new();
    for line in text.lines() {
        if let Some(v) = line.strip_prefix("Name=") {
            app = v.trim().rsplit('.').next().unwrap_or("").to_lowercase();
        } else if let Some(v) = line.strip_prefix("Title=") {
            title = v.trim().to_string();
        }
    }
    (app, title)
}

// ---------------------------------------------------------------- listings

/// `bsdtar -tvf <args>`'s output, or None if bsdtar failed.
fn bsdtar_list(args: &[&std::ffi::OsStr]) -> Option<String> {
    let out = Command::new(BSDTAR)
        .arg("-tvf")
        .args(args)
        .stdin(Stdio::null())
        .stderr(Stdio::null())
        .output()
        .ok()?;
    out.status
        .success()
        .then(|| String::from_utf8_lossy(&out.stdout).into_owned())
}

/// The member of `path` matching `member` (e.g. `data.tar*`), fed to a second
/// bsdtar run with `second` arguments; returns that run's output.
fn bsdtar_pipe(path: &Path, member: &str, second: &[&str]) -> Option<Vec<u8>> {
    let mut first = Command::new(BSDTAR)
        .args(["-xOf"])
        .arg(path)
        .arg(member)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .ok()?;
    let stdout = first.stdout.take()?;
    let out = Command::new(BSDTAR)
        .args(second)
        .stdin(stdout)
        .stderr(Stdio::null())
        .output()
        .ok()?;
    let _ = first.wait();
    (!out.stdout.is_empty()).then_some(out.stdout)
}

/// One entry of a `bsdtar -tv` listing: (mode, path).
fn listing_entries(listing: &str) -> impl Iterator<Item = (&str, &str)> {
    listing.lines().filter_map(|line| {
        // mode links owner group size month day year|time name [-> target]
        let mut fields = line.split_whitespace();
        let mode = fields.next()?;
        // Skip to the name: it follows the 8th field and may contain spaces.
        let mut rest = line.trim_start();
        for _ in 0..8 {
            let (_, after) = rest.split_once(char::is_whitespace)?;
            rest = after.trim_start();
        }
        let name = rest.split(" -> ").next().unwrap_or(rest);
        Some((mode, name))
    })
}

/// What a listing says about a package's contents.
#[derive(Debug, Default, PartialEq, Eq)]
pub struct Contents {
    pub programs: Vec<String>,
    pub program_paths: Vec<String>,
    pub desktop_files: Vec<String>,
    pub icons: Vec<String>,
    pub build_system: String,
    pub root: String,
    pub electron: bool,
}

impl Contents {
    fn fill(self, out: &mut Inspection) {
        out.programs = self.programs;
        out.program_paths = self.program_paths;
        out.desktop_files = self.desktop_files;
        out.icons = self.icons;
        out.build_system = self.build_system;
        out.root = self.root;
        out.electron = self.electron;
    }
}

/// Files that tell how a source tree is built, best first.
const BUILD_MARKERS: &[(&str, &str)] = &[
    ("Cargo.toml", "cargo"),
    ("go.mod", "go"),
    ("meson.build", "meson"),
    ("CMakeLists.txt", "cmake"),
    ("configure", "autotools"),
    ("configure.ac", "autoreconf"),
    ("Makefile", "make"),
    ("pyproject.toml", "python"),
    ("setup.py", "python"),
];

/// Programs, desktop entries, icons, the build system and the top-level directory
/// of a `bsdtar -tv` listing. Programs are files and links in a `bin` directory,
/// and with `top_level` (archives) also executables at the top (`foo/foo`, `foo`).
pub fn contents(listing: &str, top_level: bool) -> Contents {
    let mut c = Contents::default();
    let mut roots: Vec<String> = Vec::new();
    let mut at_root_level = false;
    let mut markers: Vec<(usize, &str)> = Vec::new();
    for (mode, name) in listing_entries(listing) {
        let path = name.trim_start_matches("./").trim_end_matches('/');
        let parts: Vec<&str> = path.split('/').filter(|p| !p.is_empty()).collect();
        let Some(&file) = parts.last() else { continue };
        match parts.len() {
            1 if !mode.starts_with('d') => at_root_level = true,
            _ => {
                if !roots.iter().any(|r| r == parts[0]) {
                    roots.push(parts[0].to_string());
                }
            }
        }
        if mode.starts_with('d') || file.starts_with('.') {
            continue;
        }
        if matches!(
            file,
            "chrome-sandbox" | "app.asar" | "resources.pak" | "libffmpeg.so"
        ) {
            c.electron = true;
        }
        // Build markers at the top, or one directory down.
        if parts.len() <= 2 {
            if let Some(i) = BUILD_MARKERS.iter().position(|(m, _)| *m == file) {
                markers.push((i, BUILD_MARKERS[i].1));
            }
        }
        if file.ends_with(".desktop") && path.contains("applications/") {
            c.desktop_files.push(path.to_string());
            continue;
        }
        let lower = file.to_lowercase();
        if (lower.ends_with(".png") || lower.ends_with(".svg"))
            && (path.contains("share/icons/")
                || path.contains("share/pixmaps/")
                || (parts.len() <= 3 && (lower.contains("icon") || lower.contains("logo"))))
        {
            c.icons.push(path.to_string());
            continue;
        }
        if file.contains(".so") {
            continue;
        }
        let parent = parts.len().checked_sub(2).map(|i| parts[i]);
        let in_bin = matches!(parent, Some("bin" | "sbin" | "games"));
        let executable = mode.starts_with('l') || mode.contains('x');
        let at_top = top_level && parts.len() <= 2 && executable && !file.contains('.');
        if ((in_bin && executable) || at_top)
            && c.programs.len() < MAX_PROGRAMS
            && !c.programs.iter().any(|p| p == file)
        {
            c.programs.push(file.to_string());
            c.program_paths.push(path.to_string());
        }
    }
    markers.sort();
    c.build_system = markers
        .first()
        .map(|(_, s)| s.to_string())
        .unwrap_or_default();
    if top_level && roots.len() == 1 && !at_root_level {
        c.root = roots.remove(0);
    }
    c
}

/// The programs of a listing (see [`contents`]).
pub fn programs(listing: &str, top_level: bool) -> Vec<String> {
    contents(listing, top_level).programs
}

// ------------------------------------------------------------------ names

/// Suffixes stripped from download names, longest first.
const SUFFIXES: &[&str] = &[
    ".pkg.tar.zst",
    ".flatpakref",
    ".tar.bz2",
    ".tar.zst",
    ".appimage",
    ".tar.gz",
    ".tar.xz",
    ".tgz",
    ".deb",
    ".rpm",
    ".zip",
    ".run",
    ".bin",
    ".sh",
];

const PLATFORM_WORDS: &[&str] = &[
    "linux",
    "x86",
    "amd64",
    "x64",
    "aarch64",
    "arm64",
    "setup",
    "installer",
    "portable",
];

/// A package name guessed from a download's file name.
///
/// `vlc_3.0.21-1_amd64.deb` -> vlc, `frob-1.0.tar.gz` -> frob,
/// `Obsidian-1.6.7.AppImage` -> obsidian, `foo-bar-linux-x86_64.tar.xz` -> foo-bar.
pub fn name_from_file(path: &str) -> String {
    let base = path.rsplit('/').next().unwrap_or(path);
    let lower = base.to_lowercase();
    let mut stem = base;
    if let Some(suffix) = SUFFIXES.iter().find(|s| lower.ends_with(*s)) {
        stem = &base[..base.len() - suffix.len()];
    }
    // Cut at the first separator followed by a digit, `v<digit>` or a platform word.
    let bytes = stem.as_bytes();
    let mut cut = stem.len();
    for (i, &b) in bytes.iter().enumerate() {
        if i == 0 || !matches!(b, b'-' | b'_' | b'.') {
            continue;
        }
        let rest = &stem[i + 1..];
        let rest_lower = rest.to_lowercase();
        let digit = rest.chars().next().is_some_and(|c| c.is_ascii_digit());
        let vdigit =
            rest_lower.starts_with('v') && rest.chars().nth(1).is_some_and(|c| c.is_ascii_digit());
        if digit || vdigit || PLATFORM_WORDS.iter().any(|w| rest_lower.starts_with(w)) {
            cut = i;
            break;
        }
    }
    let mut name = String::new();
    for c in stem[..cut].chars() {
        if c.is_ascii_alphanumeric() {
            name.push(c.to_ascii_lowercase());
        } else if !name.ends_with('-') {
            name.push('-');
        }
    }
    let name = name.trim_matches('-').to_string();
    if name.is_empty() {
        "software".into()
    } else {
        name
    }
}

/// The version in a download's file name, where [`name_from_file`] cuts:
/// `Obsidian-1.6.7.AppImage` -> 1.6.7, `tool-v2.1-x64.zip` -> 2.1,
/// `vlc_3.0.21-1_amd64.deb` -> 3.0.21; empty when there is none.
pub fn version_from_file(path: &str) -> String {
    let base = path.rsplit('/').next().unwrap_or(path);
    let lower = base.to_lowercase();
    let mut stem = base;
    if let Some(suffix) = SUFFIXES.iter().find(|s| lower.ends_with(*s)) {
        stem = &base[..base.len() - suffix.len()];
    }
    for (i, b) in stem.bytes().enumerate() {
        if i == 0 || !matches!(b, b'-' | b'_' | b'.') {
            continue;
        }
        let after = stem[i + 1..].to_lowercase();
        if PLATFORM_WORDS.iter().any(|w| after.starts_with(w)) {
            return String::new();
        }
        let rest = stem[i + 1..].trim_start_matches(['v', 'V']);
        if rest.starts_with(|c: char| c.is_ascii_digit()) {
            let version: String = rest
                .chars()
                .take_while(|c| c.is_ascii_digit() || *c == '.')
                .collect();
            return version.trim_end_matches('.').to_string();
        }
    }
    String::new()
}

/// Reads `len` bytes at `offset` (helper for the .rpm parser).
fn read_at(file: &mut std::fs::File, offset: u64, len: usize) -> std::io::Result<Vec<u8>> {
    file.seek(SeekFrom::Start(offset))?;
    let mut buf = vec![0u8; len];
    file.read_exact(&mut buf)?;
    Ok(buf)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn kinds_from_magic() {
        assert_eq!(
            kind_of(b"\x7fELF\x02\x01\x01\x00AI\x02", "x"),
            Kind::AppImage
        );
        assert_eq!(
            kind_of(b"\x7fELF\x02\x01\x01\x00\x00\x00\x00", "x"),
            Kind::Binary
        );
        assert_eq!(kind_of(b"!<arch>\ndebian-binary", "x"), Kind::Deb);
        assert_eq!(kind_of(&[0xed, 0xab, 0xee, 0xdb, 3, 0], "x"), Kind::Rpm);
        assert_eq!(kind_of(b"PK\x03\x04", "x"), Kind::Archive);
        assert_eq!(kind_of(&[0x1f, 0x8b, 8], "x"), Kind::Archive);
        assert_eq!(kind_of(b"[Flatpak Ref]\nName=x", "x"), Kind::FlatpakRef);
        assert_eq!(kind_of(b"#!/bin/sh\n", "x"), Kind::Installer);
        assert_eq!(kind_of(b"hello", "x"), Kind::Unknown);
    }

    #[test]
    fn names_from_files() {
        assert_eq!(name_from_file("vlc_3.0.21-1_amd64.deb"), "vlc");
        assert_eq!(name_from_file("/tmp/frob-1.0.tar.gz"), "frob");
        assert_eq!(name_from_file("Obsidian-1.6.7.AppImage"), "obsidian");
        assert_eq!(name_from_file("foo-bar-linux-x86_64.tar.xz"), "foo-bar");
        assert_eq!(name_from_file("tool-v2.1-x64.zip"), "tool");
        assert_eq!(name_from_file("Some App.run"), "some-app");
        assert_eq!(name_from_file("1.0.tar.gz"), "1");
        assert_eq!(name_from_file(".zip"), "software");
    }

    #[test]
    fn versions_from_files() {
        assert_eq!(version_from_file("Obsidian-1.6.7.AppImage"), "1.6.7");
        assert_eq!(version_from_file("tool-v2.1-x64.zip"), "2.1");
        assert_eq!(version_from_file("vlc_3.0.21-1_amd64.deb"), "3.0.21");
        assert_eq!(version_from_file("foo-bar-linux-x86_64.tar.xz"), "");
    }

    #[test]
    fn debian_control() {
        let text = "Package: vlc\nVersion: 3.0.21-1\nProvides: mp3-decoder, vlc-plugin (= 3)\n\
                    Description: multimedia player\n This is the long part.\n";
        let fields = parse_control(text);
        assert_eq!(fields[0], ("Package".into(), "vlc".into()));
        assert_eq!(split_relations(&fields[2].1), ["mp3-decoder", "vlc-plugin"]);
        assert_eq!(fields[3].1, "multimedia player\nThis is the long part.");
    }

    #[test]
    fn flatpak_refs() {
        let (app, title) =
            parse_flatpakref("[Flatpak Ref]\nName=org.videolan.VLC\nTitle=VLC media player\n");
        assert_eq!(app, "vlc");
        assert_eq!(title, "VLC media player");
    }

    #[test]
    fn programs_in_listings() {
        let deb = "\
drwxr-xr-x  0 root   root        0 Jan  1  2024 ./usr/bin/
-rwxr-xr-x  0 root   root    12345 Jan  1  2024 ./usr/bin/frob
lrwxrwxrwx  0 root   root        0 Jan  1  2024 ./usr/bin/frobctl -> frob
-rw-r--r--  0 root   root      100 Jan  1  2024 ./usr/share/doc/frob/README
-rwxr-xr-x  0 root   root    12345 Jan  1  2024 ./usr/lib/frob/libfrob.so.1
";
        assert_eq!(programs(deb, false), ["frob", "frobctl"]);
        let tarball = "\
drwxr-xr-x  0 me     me          0 Jan  1 12:00 tool-1.0/
-rwxr-xr-x  0 me     me      54321 Jan  1 12:00 tool-1.0/tool
-rw-r--r--  0 me     me        900 Jan  1 12:00 tool-1.0/README.md
-rwxr-xr-x  0 me     me        900 Jan  1 12:00 tool-1.0/install.sh
-rwxr-xr-x  0 me     me        900 Jan  1 12:00 tool-1.0/My Helper
";
        assert_eq!(programs(tarball, true), ["tool", "My Helper"]);
        assert!(programs(tarball, false).is_empty());
    }

    #[test]
    fn contents_of_packages_and_sources() {
        let deb = "\
-rwxr-xr-x  0 root   root    12345 Jan  1  2024 ./opt/Frob/frob
lrwxrwxrwx  0 root   root        0 Jan  1  2024 ./usr/bin/frob -> /opt/Frob/frob
-rw-r--r--  0 root   root      300 Jan  1  2024 ./usr/share/applications/frob.desktop
-rw-r--r--  0 root   root     9000 Jan  1  2024 ./usr/share/icons/hicolor/256x256/apps/frob.png
";
        let c = contents(deb, false);
        assert_eq!(c.programs, ["frob"]);
        assert_eq!(c.program_paths, ["usr/bin/frob"]);
        assert_eq!(c.desktop_files, ["usr/share/applications/frob.desktop"]);
        assert_eq!(c.icons, ["usr/share/icons/hicolor/256x256/apps/frob.png"]);
        assert_eq!((c.build_system.as_str(), c.root.as_str()), ("", ""));

        let source = "\
drwxr-xr-x  0 me     me          0 Jan  1 12:00 frob-1.0/
-rw-r--r--  0 me     me        900 Jan  1 12:00 frob-1.0/CMakeLists.txt
-rw-r--r--  0 me     me        900 Jan  1 12:00 frob-1.0/Makefile
-rw-r--r--  0 me     me        900 Jan  1 12:00 frob-1.0/src/main.c
-rw-r--r--  0 me     me        900 Jan  1 12:00 frob-1.0/data/logo.png
";
        let c = contents(source, true);
        assert_eq!(c.build_system, "cmake");
        assert_eq!(c.root, "frob-1.0");
        assert_eq!(c.icons, ["frob-1.0/data/logo.png"]);
        assert!(c.programs.is_empty());

        let flat = "-rwxr-xr-x  0 me     me      54321 Jan  1 12:00 tool\n";
        let c = contents(flat, true);
        assert_eq!(
            (c.programs, c.root),
            (vec!["tool".to_string()], String::new())
        );
    }
}
