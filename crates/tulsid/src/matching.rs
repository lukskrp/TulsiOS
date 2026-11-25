//! `Match`: from what someone tried to install to TulsiOS packages (ADR 0018).
//!
//! In order, each with a reason people can read:
//! 1. the curated table of other systems' names (data/name-map.json), which can
//!    also point at a NixOS service;
//! 2. the name as a package: exact attribute, a tool's package set (`pip` →
//!    `python3Packages.x`), other distributions' naming rules (`python3-x`,
//!    `libfoo-dev`, `golang-x`…), then exact pname;
//! 3. the programs inside the download (or the name, as a command) in the program
//!    index (nix/packages/program-index.nix);
//! 4. a fuzzy search on the first name.

use std::collections::HashMap;
use std::path::Path;

use tulsi_client::{Candidate, MatchHint, PackageInfo};

use crate::index::Index;

/// Other systems' names whose TulsiOS name differs (data/name-map.json).
const NAME_MAP: &str = include_str!("../../../data/name-map.json");

/// Which program comes from which packages, built from nix-index's database.
#[derive(Default)]
pub struct ProgramIndex {
    /// program -> attrs, best first.
    programs: HashMap<String, Vec<String>>,
}

impl ProgramIndex {
    /// Loads a `program<TAB>attr` file, keeping only attributes the package
    /// index has (the database may be a little older or newer than tulsipkgs).
    pub fn load(path: &Path, index: &Index) -> Result<Self, String> {
        let text = std::fs::read_to_string(path)
            .map_err(|e| format!("cannot read program index {}: {e}", path.display()))?;
        Ok(Self::from_tsv(&text, index))
    }

    pub fn from_tsv(text: &str, index: &Index) -> Self {
        let mut programs: HashMap<String, Vec<String>> = HashMap::new();
        for line in text.lines() {
            let Some((program, attr)) = line.split_once('\t') else {
                continue;
            };
            if !index.contains(attr) {
                continue;
            }
            let attrs = programs.entry(program.to_string()).or_default();
            if !attrs.iter().any(|a| a == attr) {
                attrs.push(attr.to_string());
            }
        }
        for (program, attrs) in programs.iter_mut() {
            // The package named like the program, then top-level, then shorter names.
            attrs.sort_by_key(|a| (a != program, a.contains('.'), a.len(), a.clone()));
        }
        Self { programs }
    }

    pub fn len(&self) -> usize {
        self.programs.len()
    }

    pub fn get(&self, program: &str) -> &[String] {
        self.programs.get(program).map_or(&[], Vec::as_slice)
    }
}

/// The curated table: lower-case name -> attributes or `service:<name>`.
pub struct NameMap(HashMap<String, Vec<String>>);

impl NameMap {
    pub fn builtin() -> Self {
        let raw: HashMap<String, serde_json::Value> =
            serde_json::from_str(NAME_MAP).expect("data/name-map.json is valid");
        Self(
            raw.into_iter()
                .filter(|(k, _)| !k.starts_with('_'))
                .filter_map(|(k, v)| Some((k, serde_json::from_value(v).ok()?)))
                .collect(),
        )
    }

    fn get(&self, name: &str) -> &[String] {
        self.0.get(&name.to_lowercase()).map_or(&[], Vec::as_slice)
    }
}

/// Names a package set of `tool` would use for `name`: (attribute, reason).
fn tool_attrs(tool: &str, name: &str) -> Vec<(String, String)> {
    let lower = name.to_lowercase();
    // PyPI names ignore case and treat `_`, `.` and `-` alike; nixpkgs uses `-`.
    let py = lower.replace(['_', '.'], "-");
    let via = |attr: String, what: &str| (attr, format!("{what} `{name}` in TulsiOS"));
    match tool {
        "pip" | "pip3" => vec![
            via(format!("python3Packages.{py}"), "the Python package"),
            via(py.clone(), "the Python package"),
        ],
        "pipx" => vec![
            via(py.clone(), "the Python program"),
            via(format!("python3Packages.{py}"), "the Python program"),
        ],
        "npm" => {
            let bare = lower.rsplit('/').next().unwrap_or(&lower).to_string();
            vec![
                via(bare.clone(), "the npm package"),
                via(format!("nodePackages.{bare}"), "the npm package"),
            ]
        }
        "gem" => vec![
            via(lower.clone(), "the Ruby gem"),
            via(format!("rubyPackages.{lower}"), "the Ruby gem"),
        ],
        "cargo" => vec![via(lower.clone(), "the Rust crate")],
        "go" => {
            // `go install github.com/x/tool/cmd/tool@latest` -> tool
            let last = lower.rsplit('/').next().unwrap_or(&lower).to_string();
            vec![via(last, "the Go program")]
        }
        _ => Vec::new(),
    }
}

/// What other distributions' naming conventions say the nixpkgs name is:
/// (attribute or pname, reason).
fn distro_attrs(name: &str) -> Vec<(String, String)> {
    let lower = name.to_lowercase();
    let mut out: Vec<(String, String)> = Vec::new();
    let mut push = |attr: String, why: &str| {
        if !attr.is_empty() && !out.iter().any(|(a, _)| *a == attr) {
            out.push((attr, format!("`{name}` {why}")));
        }
    };
    let prefixed = [
        ("python3-", "python3Packages.", "is a Python package"),
        ("python-", "python3Packages.", "is a Python package"),
        ("py3-", "python3Packages.", "is a Python package"),
        ("node-", "nodePackages.", "is an npm package"),
        ("r-cran-", "rPackages.", "is an R package"),
        ("ruby-", "rubyPackages.", "is a Ruby gem"),
        ("rubygem-", "rubyPackages.", "is a Ruby gem"),
        ("perl-", "perlPackages.", "is a Perl module"),
        ("lua-", "luaPackages.", "is a Lua module"),
        ("haskell-", "haskellPackages.", "is a Haskell package"),
        ("ghc-", "haskellPackages.", "is a Haskell package"),
    ];
    for (prefix, set, why) in prefixed {
        if let Some(rest) = lower.strip_prefix(prefix) {
            push(format!("{set}{rest}"), why);
        }
    }
    // golang-github-foo-bar-dev -> bar; golang-foo -> foo
    if let Some(rest) = lower.strip_prefix("golang-") {
        let rest = rest.trim_end_matches("-dev");
        push(rest.to_string(), "is a Go package");
        if let Some(last) = rest.rsplit('-').next() {
            push(last.to_string(), "is a Go package");
        }
    }
    // foo-dev, foo-devel, foo-bin, … -> foo; libfoo3 -> foo
    let mut base = lower.clone();
    for suffix in [
        "-devel", "-dev", "-bin", "-common", "-utils", "-tools", "-cli", "-data", "-git",
    ] {
        if let Some(stripped) = base.strip_suffix(suffix) {
            base = stripped.to_string();
            break;
        }
    }
    if base != lower {
        push(base.clone(), "is part of this package");
    }
    if let Some(lib) = base.strip_prefix("lib") {
        let lib = lib.trim_end_matches(|c: char| c.is_ascii_digit() || c == '.' || c == '-');
        let lib = lib.trim_end_matches("t64");
        push(lib.to_string(), "is this library");
        push(format!("lib{lib}"), "is this library");
    }
    out
}

/// Candidates for `hint`, best first, at most `limit`. Service candidates have
/// `enabled: false`; the caller marks the ones state.json has on.
pub fn find(
    index: &Index,
    programs: &ProgramIndex,
    names: &NameMap,
    hint: &MatchHint,
    limit: usize,
) -> Vec<Candidate> {
    let mut out: Vec<Candidate> = Vec::new();
    let mut seen: Vec<String> = Vec::new();
    let mut add = |out: &mut Vec<Candidate>, info: PackageInfo, reason: String| {
        if !seen.contains(&info.attr) {
            seen.push(info.attr.clone());
            out.push(Candidate::Package { info, reason });
        }
    };
    let names_in_order: Vec<&String> = hint
        .names
        .iter()
        .chain(&hint.provides)
        .filter(|n| !n.trim().is_empty())
        .collect();

    for name in &names_in_order {
        let name = name.trim();
        // 1. The curated table.
        for target in names.get(name) {
            if let Some(service) = target.strip_prefix("service:") {
                let service = service.to_string();
                if !out
                    .iter()
                    .any(|c| matches!(c, Candidate::Service { name, .. } if *name == service))
                {
                    out.push(Candidate::Service {
                        reason: format!("`{name}` is the {service} service on TulsiOS"),
                        name: service,
                        enabled: false,
                    });
                }
            } else if let Some(info) = index.get(target) {
                add(&mut out, info, format!("TulsiOS's name for `{name}`"));
            }
        }
        // 2. The name itself, the tool's package set, other distributions' rules.
        if let Some(info) = index.get(name) {
            add(&mut out, info, format!("named `{name}`"));
        }
        for (attr, reason) in tool_attrs(&hint.tool, name)
            .into_iter()
            .chain(distro_attrs(name))
        {
            if let Some(info) = index.get(&attr) {
                add(&mut out, info, reason);
            } else {
                for info in index.by_pname(&attr).into_iter().take(1) {
                    add(&mut out, info, reason.clone());
                }
            }
        }
        for info in index.by_pname(name).into_iter().take(2) {
            add(&mut out, info, format!("named `{name}`"));
        }
    }

    // 3. Programs inside the download, then the names as commands.
    let commands = hint
        .programs
        .iter()
        .map(|p| (p.as_str(), true))
        .chain(names_in_order.iter().map(|n| (n.as_str(), false)));
    for (program, inside) in commands {
        for attr in programs.get(program).iter().take(3) {
            if let Some(info) = index.get(attr) {
                let reason = if inside {
                    format!("provides the program `{program}` that this contains")
                } else {
                    format!("provides the command `{program}`")
                };
                add(&mut out, info, reason);
            }
        }
    }

    // 4. Similar names.
    if out.len() < limit {
        if let Some(first) = names_in_order.first() {
            for info in index.search(first, limit) {
                add(&mut out, info, format!("similar to `{}`", first.trim()));
            }
        }
    }
    out.truncate(limit);
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    const INDEX: &str = r#"[
        ["bat","bat","0.25","A cat clone with wings",false],
        ["fd","fd","10.2","Simple, fast alternative to find",false],
        ["firefox","firefox","145.0","Web browser",false],
        ["gcc","gcc-wrapper","14","GNU Compiler Collection",false],
        ["gnumake","gnumake","4.4","A tool to control the generation of non-source files",false],
        ["htop","htop","3.5","An interactive process viewer",false],
        ["htop-vim","htop-vim","3.5","htop with vim keys",false],
        ["libsodium","libsodium","1.0","A modern crypto library",false],
        ["nodePackages.prettier","prettier","3.0","Code formatter",false],
        ["python3Packages.requests","requests","2.32","HTTP library for Python",false],
        ["python3Packages.scikit-learn","scikit-learn","1.5","Machine learning in Python",false],
        ["ripgrep","ripgrep","15.2","Line-oriented search tool",false],
        ["vlc","vlc","3.0.24","Cross-platform media player",false],
        ["vscode","vscode","1.100","Code editor",true]
    ]"#;

    const PROGRAMS: &str =
        "rg\tripgrep\nhtop\thtop-vim\nhtop\thtop\nvlc\tvlc\ncvlc\tvlc\nfrob\tnot-in-index\n";

    fn run(hint: MatchHint) -> Vec<String> {
        let index = Index::from_json(INDEX).unwrap();
        let programs = ProgramIndex::from_tsv(PROGRAMS, &index);
        find(&index, &programs, &NameMap::builtin(), &hint, 5)
            .into_iter()
            .map(|c| match c {
                Candidate::Package { info, .. } => info.attr,
                Candidate::Service { name, .. } => format!("service:{name}"),
            })
            .collect()
    }

    fn names(n: &[&str]) -> MatchHint {
        MatchHint {
            names: n.iter().map(|s| s.to_string()).collect(),
            ..Default::default()
        }
    }

    #[test]
    fn curated_names_and_services() {
        assert_eq!(run(names(&["build-essential"]))[..2], ["gcc", "gnumake"]);
        assert_eq!(run(names(&["code"]))[0], "vscode");
        assert_eq!(run(names(&["fd-find"]))[0], "fd");
        assert_eq!(run(names(&["openssh-server"]))[0], "service:openssh");
    }

    #[test]
    fn distro_naming_rules() {
        assert_eq!(
            run(names(&["python3-requests"]))[0],
            "python3Packages.requests"
        );
        assert_eq!(run(names(&["libsodium-dev"]))[0], "libsodium");
        assert_eq!(run(names(&["libsodium23"]))[0], "libsodium");
        assert_eq!(run(names(&["node-prettier"]))[0], "nodePackages.prettier");
    }

    #[test]
    fn tools() {
        let pip = MatchHint {
            names: vec!["Scikit_Learn".into()],
            tool: "pip".into(),
            ..Default::default()
        };
        assert_eq!(run(pip)[0], "python3Packages.scikit-learn");
        let npm = MatchHint {
            names: vec!["prettier".into()],
            tool: "npm".into(),
            ..Default::default()
        };
        assert_eq!(run(npm)[0], "nodePackages.prettier");
    }

    #[test]
    fn programs_inside_and_commands() {
        let deb = MatchHint {
            names: vec!["frobnicate-player".into()],
            programs: vec!["cvlc".into()],
            ..Default::default()
        };
        assert_eq!(run(deb)[0], "vlc");
        // The package named like the program first; unknown attrs are dropped.
        assert_eq!(run(names(&["rg"]))[0], "ripgrep");
        assert_eq!(run(names(&["htop"]))[..2], ["htop", "htop-vim"]);
        assert!(run(names(&["frob"])).is_empty());
    }

    #[test]
    fn provides_and_fuzzy_last() {
        let hint = MatchHint {
            names: vec!["vlc-nightly".into()],
            provides: vec!["vlc".into()],
            ..Default::default()
        };
        assert_eq!(run(hint)[0], "vlc");
        assert_eq!(run(names(&["fire"]))[0], "firefox");
    }
}
