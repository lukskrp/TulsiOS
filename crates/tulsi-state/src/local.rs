//! Static checks on a local package's Nix expression (tulsid before applying it,
//! tulsi-mcp before building it). The expression is evaluated by the system rebuild as
//! root, so on top of the person's review this refuses anything that reads the host,
//! fetches impurely or weakens the build sandbox.

/// Largest accepted expression.
const MAX_EXPRESSION: usize = 64 * 1024;

/// Builtins and attributes that read the host, fetch impurely or weaken the sandbox.
const FORBIDDEN: &[&str] = &[
    "builtins.readFile",
    "builtins.readDir",
    "builtins.readFileType",
    "builtins.pathExists",
    "builtins.getEnv",
    "builtins.exec",
    "builtins.fetch",
    "builtins.getFlake",
    "builtins.storePath",
    "builtins.path",
    "builtins.filterSource",
    "builtins.findFile",
    "builtins.currentSystem",
    "builtins.unsafe",
    "builtins.importNative",
    "builtins.scopedImport",
    "__noChroot",
    "__impureHostDeps",
    "__structuredAttrs",
    "allowSubstitutes",
    "impureEnvVars",
    "requiredSystemFeatures",
    "unsafeDiscardStringContext",
    "import <",
    "<nixpkgs",
    "${/",
];

/// Static checks on an expression; returns every problem found.
pub fn check_expression(expr: &str) -> Vec<String> {
    let mut problems = Vec::new();
    if expr.len() > MAX_EXPRESSION {
        problems.push(format!(
            "the expression is too large ({} bytes, at most {MAX_EXPRESSION})",
            expr.len()
        ));
        return problems;
    }
    let code = strip_strings_and_comments(expr);
    if !code.trim_start().starts_with('{') {
        problems.push(
            "the expression must be a function of its dependencies, e.g. \
             `{ stdenv, fetchurl }: stdenv.mkDerivation { … }`"
                .into(),
        );
    }
    for word in FORBIDDEN {
        if expr.contains(word) {
            problems.push(format!("`{word}` is not allowed in a local package"));
        }
    }
    if let Some(path) = find_path_literal(&code) {
        problems.push(format!(
            "path literals such as `{path}` are not allowed; fetch sources with a hashed \
             fetcher (fetchurl, fetchzip, fetchFromGitHub)"
        ));
    }
    problems
}

/// Replaces the contents of strings and comments with spaces, keeping `${…}`
/// interpolations (which are code) and line breaks intact.
pub(crate) fn strip_strings_and_comments(src: &str) -> String {
    let b: Vec<char> = src.chars().collect();
    let blank = |c: char| if c == '\n' { '\n' } else { ' ' };
    let mut out = String::with_capacity(src.len());
    let mut i = 0;
    while i < b.len() {
        let c = b[i];
        if c == '#' {
            while i < b.len() && b[i] != '\n' {
                out.push(' ');
                i += 1;
            }
        } else if c == '/' && b.get(i + 1) == Some(&'*') {
            while i < b.len() && !(b[i] == '*' && b.get(i + 1) == Some(&'/')) {
                out.push(blank(b[i]));
                i += 1;
            }
            out.push_str("  ");
            i += 2;
        } else if c == '"' {
            out.push('"');
            i += 1;
            while i < b.len() && b[i] != '"' {
                if b[i] == '\\' {
                    out.push_str("  ");
                    i += 2;
                } else if b[i] == '$' && b.get(i + 1) == Some(&'{') {
                    i = copy_interpolation(&b, i, &mut out);
                } else {
                    out.push(blank(b[i]));
                    i += 1;
                }
            }
            out.push('"');
            i += 1;
        } else if c == '\'' && b.get(i + 1) == Some(&'\'') {
            out.push_str("''");
            i += 2;
            while i < b.len() {
                if b[i] == '\'' && b.get(i + 1) == Some(&'\'') {
                    // ''' , ''$ and ''\x are escapes inside indented strings.
                    match b.get(i + 2) {
                        Some('\'') | Some('$') => {
                            out.push_str("   ");
                            i += 3;
                        }
                        Some('\\') => {
                            out.push_str("    ");
                            i += 4;
                        }
                        _ => {
                            out.push_str("''");
                            i += 2;
                            break;
                        }
                    }
                } else if b[i] == '$' && b.get(i + 1) == Some(&'{') {
                    i = copy_interpolation(&b, i, &mut out);
                } else {
                    out.push(if b[i] == '\n' { '\n' } else { ' ' });
                    i += 1;
                }
            }
        } else {
            out.push(c);
            i += 1;
        }
    }
    out
}

/// Copies a `${ … }` interpolation starting at `i` (stripping nested strings);
/// returns the index after it.
fn copy_interpolation(b: &[char], start: usize, out: &mut String) -> usize {
    let mut depth = 0usize;
    let mut i = start;
    let mut inner = String::new();
    while i < b.len() {
        inner.push(b[i]);
        match b[i] {
            '{' => depth += 1,
            '}' => {
                depth -= 1;
                if depth == 0 {
                    i += 1;
                    break;
                }
            }
            _ => {}
        }
        i += 1;
    }
    out.push_str(&strip_strings_and_comments(&inner));
    i
}

/// A Nix path literal in code (`/etc/x`, `./x`, `../x`, `~/x`).
pub(crate) fn find_path_literal(code: &str) -> Option<String> {
    let chars: Vec<char> = code.chars().collect();
    for i in 0..chars.len() {
        let prev_ok =
            i == 0 || !(chars[i - 1].is_ascii_alphanumeric() || "_'-.$}/".contains(chars[i - 1]));
        if !prev_ok {
            continue;
        }
        let rest: String = chars[i..chars.len().min(i + 3)].iter().collect();
        let starts = rest.starts_with("./")
            || rest.starts_with("../")
            || rest.starts_with("~/")
            || (rest.starts_with('/')
                && chars
                    .get(i + 1)
                    .is_some_and(|c| c.is_ascii_alphanumeric() || *c == '.'));
        if starts {
            let end = chars[i..]
                .iter()
                .position(|c| c.is_whitespace() || ";)]}".contains(*c))
                .map_or(chars.len(), |p| i + p);
            return Some(chars[i..end].iter().collect());
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    const GOOD: &str = r#"
{ lib, stdenv, fetchurl, autoPatchelfHook, makeWrapper, zlib }:
# A prebuilt binary tarball.
stdenv.mkDerivation (finalAttrs: {
  pname = "frob";
  version = "1.2.3";
  src = fetchurl {
    url = "https://example.com/frob-${finalAttrs.version}-linux-x86_64.tar.gz";
    hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
  };
  nativeBuildInputs = [ autoPatchelfHook makeWrapper ];
  buildInputs = [ zlib ];
  installPhase = ''
    mkdir -p $out/bin
    cp frob $out/bin/
    ln -s /dev/null $out/null  # a path inside a shell string is fine
  '';
  meta.description = "Frobnicates things";
})
"#;

    #[test]
    fn a_normal_package_passes() {
        assert_eq!(check_expression(GOOD), Vec::<String>::new());
    }

    #[test]
    fn reading_the_host_is_refused() {
        let bad = GOOD.replace(
            "buildInputs = [ zlib ];",
            "buildInputs = [ zlib ]; x = builtins.readFile /etc/shadow;",
        );
        let problems = check_expression(&bad);
        assert!(
            problems.iter().any(|p| p.contains("builtins.readFile")),
            "{problems:?}"
        );
        assert!(
            problems.iter().any(|p| p.contains("/etc/shadow")),
            "{problems:?}"
        );
    }

    #[test]
    fn interpolated_paths_and_sandbox_escapes_are_refused() {
        for bad in [
            GOOD.replace("cp frob $out/bin/", "cat ${/etc/shadow} > $out/x"),
            GOOD.replace("pname = \"frob\";", "pname = \"frob\"; __noChroot = true;"),
            GOOD.replace("src = fetchurl {", "src = ./frob.tar.gz; x = fetchurl {"),
            GOOD.replace("{ lib,", "with import <nixpkgs> {}; { lib,"),
        ] {
            assert!(!check_expression(&bad).is_empty(), "{bad}");
        }
    }

    #[test]
    fn must_be_a_function() {
        assert!(!check_expression("stdenv.mkDerivation {}").is_empty());
    }
}
