//! Checks for proposed `configuration.nix` contents: size, syntax (via
//! `nix-instantiate --parse`) and a unified diff against the current file.
//! Evaluation errors are caught later by the rebuild, which restores the old
//! file on failure.

use std::path::PathBuf;
use std::process::Stdio;

use tokio::process::Command;

pub const MAX_SIZE: usize = 1024 * 1024;

/// A temporary file removed on drop.
struct TempFile(PathBuf);

impl TempFile {
    fn new(name: &str, contents: &[u8]) -> Result<Self, String> {
        let dir = std::env::temp_dir().join(format!(
            "tulsid-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or(0)
        ));
        std::fs::create_dir_all(&dir).map_err(|e| format!("cannot create temp dir: {e}"))?;
        let path = dir.join(name);
        std::fs::write(&path, contents).map_err(|e| format!("cannot write temp file: {e}"))?;
        Ok(Self(path))
    }
}

impl Drop for TempFile {
    fn drop(&mut self) {
        if let Some(dir) = self.0.parent() {
            let _ = std::fs::remove_dir_all(dir);
        }
    }
}

/// Fails with nix's own message if `contents` is not valid Nix syntax.
pub async fn check_syntax(contents: &str) -> Result<(), String> {
    if contents.len() > MAX_SIZE {
        return Err(format!("file is larger than {MAX_SIZE} bytes"));
    }
    if contents.trim().is_empty() {
        return Err("file is empty".into());
    }
    let file = TempFile::new("configuration.nix", contents.as_bytes())?;
    let out = Command::new("nix-instantiate")
        .arg("--parse")
        .arg(&file.0)
        .stdin(Stdio::null())
        .output()
        .await
        .map_err(|e| format!("cannot run nix-instantiate: {e}"))?;
    if out.status.success() {
        Ok(())
    } else {
        let msg = String::from_utf8_lossy(&out.stderr);
        let path = file.0.display().to_string();
        Err(format!(
            "not valid Nix: {}",
            msg.trim().replace(&path, "configuration.nix")
        ))
    }
}

/// Unified diff from `old` (None = file absent) to `new`, labelled with `rel`.
pub async fn diff(rel: &str, old: Option<&[u8]>, new: &[u8]) -> Result<String, String> {
    let a = TempFile::new("a", old.unwrap_or_default())?;
    let b = TempFile::new("b", new)?;
    let out = Command::new("diff")
        .args([
            "-u",
            "--label",
            &format!("a/{rel}"),
            "--label",
            &format!("b/{rel}"),
        ])
        .arg(&a.0)
        .arg(&b.0)
        .stdin(Stdio::null())
        .output()
        .await
        .map_err(|e| format!("cannot run diff: {e}"))?;
    match out.status.code() {
        Some(0) | Some(1) => Ok(String::from_utf8_lossy(&out.stdout).into_owned()),
        _ => Err(format!(
            "diff failed: {}",
            String::from_utf8_lossy(&out.stderr).trim()
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn diff_marks_changes() {
        let d = diff(
            "configuration.nix",
            Some(b"{ }\n"),
            b"{\n  services.printing.enable = true;\n}\n",
        )
        .await
        .unwrap();
        assert!(
            d.starts_with("--- a/configuration.nix\n+++ b/configuration.nix\n"),
            "{d}"
        );
        assert!(d.contains("+  services.printing.enable = true;"), "{d}");
        assert!(diff("x", Some(b"same"), b"same").await.unwrap().is_empty());
    }

    #[tokio::test]
    async fn rejects_empty_and_huge() {
        assert!(check_syntax("  ").await.is_err());
        assert!(check_syntax(&"#".repeat(MAX_SIZE + 1)).await.is_err());
    }
}
