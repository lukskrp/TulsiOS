//! Finds browser extensions the user installed imperatively from the official
//! stores, by reading the browsers' own profile files.
//!
//! Only store installs are adopted: the declarative policy re-downloads the
//! extension from the store by id, which is impossible for side-loaded ones.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use serde_json::Value;
use tulsi_state::{is_valid_chromium_id, is_valid_firefox_id, Browser};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Found {
    pub browser: Browser,
    pub id: String,
    pub name: String,
}

impl Found {
    pub fn key(&self) -> String {
        format!("{}:{}", self.browser.name(), self.id)
    }
}

/// Profile files that list installed extensions, for change detection.
pub fn watched_files(home: &Path, config: &Path) -> Vec<PathBuf> {
    let mut files = Vec::new();
    for root in firefox_roots(home, config) {
        for profile in subdirs(&root) {
            files.push(profile.join("extensions.json"));
        }
    }
    for root in chromium_roots(config) {
        for profile in subdirs(&root) {
            files.push(profile.join("Secure Preferences"));
            files.push(profile.join("Preferences"));
        }
    }
    files.retain(|f| f.is_file());
    files
}

/// All store-installed, user-installed extensions across all profiles.
pub fn scan(home: &Path, config: &Path) -> Vec<Found> {
    let mut found: BTreeMap<String, Found> = BTreeMap::new();
    for root in firefox_roots(home, config) {
        for profile in subdirs(&root) {
            if let Ok(text) = std::fs::read_to_string(profile.join("extensions.json")) {
                for f in parse_firefox(&text) {
                    found.entry(f.key()).or_insert(f);
                }
            }
        }
    }
    for root in chromium_roots(config) {
        for profile in subdirs(&root) {
            for file in ["Secure Preferences", "Preferences"] {
                if let Ok(text) = std::fs::read_to_string(profile.join(file)) {
                    for f in parse_chromium(&text, &profile) {
                        found.entry(f.key()).or_insert(f);
                    }
                }
            }
        }
    }
    found.into_values().collect()
}

/// `home` and the XDG config directory (usually `~/.config`).
fn firefox_roots(home: &Path, config: &Path) -> Vec<PathBuf> {
    vec![
        home.join(".mozilla/firefox"),
        config.join("mozilla/firefox"),
    ]
}

fn chromium_roots(config: &Path) -> Vec<PathBuf> {
    ["chromium", "google-chrome", "BraveSoftware/Brave-Browser"]
        .iter()
        .map(|d| config.join(d))
        .collect()
}

fn subdirs(dir: &Path) -> Vec<PathBuf> {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return Vec::new();
    };
    let mut dirs: Vec<PathBuf> = entries
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.is_dir())
        .collect();
    dirs.sort();
    dirs
}

/// Firefox `extensions.json`: user-installed (`app-profile`) extensions
/// downloaded from addons.mozilla.org, excluding ones policy already installed.
pub fn parse_firefox(text: &str) -> Vec<Found> {
    let Ok(json) = serde_json::from_str::<Value>(text) else {
        return Vec::new();
    };
    let Some(addons) = json["addons"].as_array() else {
        return Vec::new();
    };
    addons
        .iter()
        .filter(|a| a["type"] == "extension" && a["location"] == "app-profile")
        .filter(|a| {
            a["sourceURI"]
                .as_str()
                .is_some_and(|u| u.starts_with("https://addons.mozilla.org/"))
        })
        .filter(|a| a["installTelemetryInfo"]["source"] != "enterprise-policy")
        .filter_map(|a| {
            let id = a["id"].as_str()?.to_string();
            is_valid_firefox_id(&id).then(|| Found {
                browser: Browser::Firefox,
                name: a["defaultLocale"]["name"]
                    .as_str()
                    .unwrap_or(&id)
                    .to_string(),
                id,
            })
        })
        .collect()
}

/// Chromium-family `Secure Preferences` / `Preferences`: extensions installed
/// from the Chrome Web Store by the user (location 1 = internal).
pub fn parse_chromium(text: &str, profile: &Path) -> Vec<Found> {
    let Ok(json) = serde_json::from_str::<Value>(text) else {
        return Vec::new();
    };
    let Some(settings) = json["extensions"]["settings"].as_object() else {
        return Vec::new();
    };
    settings
        .iter()
        .filter(|(id, s)| {
            is_valid_chromium_id(id) && s["location"] == 1 && s["from_webstore"] == true
        })
        .map(|(id, s)| Found {
            browser: Browser::Chromium,
            name: chromium_name(id, s, profile).unwrap_or_else(|| id.clone()),
            id: id.clone(),
        })
        .collect()
}

/// Name from the stored manifest, else from the installed manifest.json,
/// resolving `__MSG_key__` placeholders through `_locales`.
fn chromium_name(id: &str, settings: &Value, profile: &Path) -> Option<String> {
    if let Some(name) = settings["manifest"]["name"].as_str() {
        if !name.starts_with("__MSG_") {
            return Some(name.to_string());
        }
    }
    let version_dir = subdirs(&profile.join("Extensions").join(id)).pop()?;
    let manifest: Value =
        serde_json::from_str(&std::fs::read_to_string(version_dir.join("manifest.json")).ok()?)
            .ok()?;
    let name = manifest["name"].as_str()?;
    let Some(key) = name
        .strip_prefix("__MSG_")
        .and_then(|k| k.strip_suffix("__"))
    else {
        return Some(name.to_string());
    };
    let locale = manifest["default_locale"].as_str().unwrap_or("en");
    let messages: Value = serde_json::from_str(
        &std::fs::read_to_string(
            version_dir
                .join("_locales")
                .join(locale)
                .join("messages.json"),
        )
        .ok()?,
    )
    .ok()?;
    messages
        .as_object()?
        .iter()
        .find(|(k, _)| k.eq_ignore_ascii_case(key))
        .and_then(|(_, v)| v["message"].as_str())
        .map(str::to_string)
}

#[cfg(test)]
mod tests {
    use super::*;

    const FIREFOX: &str = r#"{"schemaVersion": 36, "addons": [
      {"id": "uBlock0@raymondhill.net", "type": "extension", "location": "app-profile",
       "sourceURI": "https://addons.mozilla.org/firefox/downloads/file/1/ublock_origin.xpi",
       "defaultLocale": {"name": "uBlock Origin"}},
      {"id": "{446900e4-71c2-419f-a6a7-df9c091e268b}", "type": "extension", "location": "app-profile",
       "sourceURI": "https://addons.mozilla.org/firefox/downloads/file/2/bitwarden.xpi",
       "installTelemetryInfo": {"source": "enterprise-policy"},
       "defaultLocale": {"name": "Bitwarden"}},
      {"id": "sideloaded@example.org", "type": "extension", "location": "app-profile",
       "sourceURI": "file:///home/u/ext.xpi", "defaultLocale": {"name": "Local"}},
      {"id": "formautofill@mozilla.org", "type": "extension", "location": "app-builtin"},
      {"id": "fr@dictionaries.addons.mozilla.org", "type": "dictionary", "location": "app-profile",
       "sourceURI": "https://addons.mozilla.org/x.xpi"}
    ]}"#;

    #[test]
    fn firefox_only_store_installs_by_the_user() {
        let found = parse_firefox(FIREFOX);
        assert_eq!(found.len(), 1, "{found:?}");
        assert_eq!(found[0].id, "uBlock0@raymondhill.net");
        assert_eq!(found[0].name, "uBlock Origin");
        assert_eq!(found[0].key(), "firefox:uBlock0@raymondhill.net");
    }

    #[test]
    fn chromium_only_webstore_internal_installs() {
        let prefs = r#"{"extensions": {"settings": {
          "cjpalhdlnbpafiamejdnhcphjbkeiagm": {"location": 1, "from_webstore": true,
              "manifest": {"name": "uBlock Origin"}},
          "nngceckbapebfimnlniiiahkandclblb": {"location": 1, "from_webstore": true},
          "mhjfbmdgcfjbbpaeojofohoefgiehjai": {"location": 5},
          "abcdefghijklmnopabcdefghijklmnop": {"location": 4},
          "not-an-id": {"location": 1, "from_webstore": true}
        }}}"#;
        let found = parse_chromium(prefs, Path::new("/nonexistent"));
        let ids: Vec<&str> = found.iter().map(|f| f.id.as_str()).collect();
        assert_eq!(
            ids,
            [
                "cjpalhdlnbpafiamejdnhcphjbkeiagm",
                "nngceckbapebfimnlniiiahkandclblb"
            ]
        );
        assert_eq!(found[0].name, "uBlock Origin");
        // No manifest available: falls back to the id.
        assert_eq!(found[1].name, "nngceckbapebfimnlniiiahkandclblb");
    }

    #[test]
    fn scans_profiles_and_resolves_localized_names() {
        let home = std::env::temp_dir().join(format!("extwatch-test-{}", std::process::id()));
        let ff = home.join(".mozilla/firefox/abc.default");
        let ch = home.join(".config/chromium/Default");
        let ext = ch.join("Extensions/nngceckbapebfimnlniiiahkandclblb/2025.1.0_0");
        std::fs::create_dir_all(&ff).unwrap();
        std::fs::create_dir_all(ext.join("_locales/en")).unwrap();
        std::fs::write(ff.join("extensions.json"), FIREFOX).unwrap();
        std::fs::write(
            ch.join("Secure Preferences"),
            r#"{"extensions":{"settings":{"nngceckbapebfimnlniiiahkandclblb":{"location":1,"from_webstore":true}}}}"#,
        )
        .unwrap();
        std::fs::write(
            ext.join("manifest.json"),
            r#"{"name":"__MSG_extName__","default_locale":"en"}"#,
        )
        .unwrap();
        std::fs::write(
            ext.join("_locales/en/messages.json"),
            r#"{"extName":{"message":"Bitwarden Password Manager"}}"#,
        )
        .unwrap();

        let found = scan(&home, &home.join(".config"));
        let names: Vec<(String, String)> =
            found.iter().map(|f| (f.key(), f.name.clone())).collect();
        assert_eq!(
            names,
            [
                (
                    "chromium:nngceckbapebfimnlniiiahkandclblb".to_string(),
                    "Bitwarden Password Manager".to_string()
                ),
                (
                    "firefox:uBlock0@raymondhill.net".to_string(),
                    "uBlock Origin".to_string()
                ),
            ]
        );
        assert_eq!(watched_files(&home, &home.join(".config")).len(), 2);
        std::fs::remove_dir_all(&home).unwrap();
    }
}
