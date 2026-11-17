//! In-memory package search index (built by nix/packages/package-index.nix).
//!
//! File format: JSON array of `[attr, pname, version, description, unfree]`.

use std::collections::HashMap;
use std::path::Path;

use tulsi_client::PackageInfo;

#[derive(Debug, Clone, serde::Deserialize)]
struct Row(String, String, String, String, bool);

pub struct Index {
    entries: Vec<Row>,
    by_attr: HashMap<String, usize>,
}

impl Index {
    pub fn load(path: &Path) -> Result<Self, String> {
        let text = std::fs::read_to_string(path)
            .map_err(|e| format!("cannot read package index {}: {e}", path.display()))?;
        Self::from_json(&text)
    }

    pub fn from_json(text: &str) -> Result<Self, String> {
        let entries: Vec<Row> =
            serde_json::from_str(text).map_err(|e| format!("invalid package index: {e}"))?;
        let by_attr = entries
            .iter()
            .enumerate()
            .map(|(i, row)| (row.0.clone(), i))
            .collect();
        Ok(Self { entries, by_attr })
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn get(&self, attr: &str) -> Option<PackageInfo> {
        self.by_attr.get(attr).map(|&i| info(&self.entries[i]))
    }

    /// Best matches first: exact attribute, attribute prefix, name match,
    /// attribute substring, then all words in the description. Ties prefer
    /// free software, then shorter (usually top-level) attribute names.
    pub fn search(&self, query: &str, limit: usize) -> Vec<PackageInfo> {
        let query = query.trim().to_lowercase();
        if query.is_empty() {
            return Vec::new();
        }
        let words: Vec<&str> = query.split_whitespace().collect();

        let mut hits: Vec<(u8, usize, &Row)> = self
            .entries
            .iter()
            .filter_map(|row| score(row, &query, &words).map(|s| (s, row.0.len(), row)))
            .collect();
        hits.sort_by(|a, b| (a.0, a.2 .4, a.1, &a.2 .0).cmp(&(b.0, b.2 .4, b.1, &b.2 .0)));
        hits.into_iter()
            .take(limit)
            .map(|(_, _, row)| info(row))
            .collect()
    }

    /// Up to `n` attribute names similar to `attr`, for "did you mean" hints:
    /// close typos first (edit distance ≤ 2 on top-level names), then
    /// search matches.
    pub fn suggest(&self, attr: &str, n: usize) -> Vec<String> {
        let wanted = attr.to_lowercase();
        // A swapped letter pair ("vcl" for "vlc") is distance 2.
        let max_distance = if wanted.chars().count() <= 2 { 1 } else { 2 };
        let mut close: Vec<(usize, &str)> = self
            .entries
            .iter()
            .map(|row| row.0.as_str())
            .filter(|a| !a.contains('.'))
            .filter_map(|a| {
                let d = levenshtein(&wanted, &a.to_lowercase(), max_distance)?;
                Some((d, a))
            })
            .collect();
        close.sort_by_key(|&(d, a)| (d, a.len(), a));

        let mut out: Vec<String> = close.into_iter().map(|(_, a)| a.to_string()).collect();
        for p in self.search(attr, n) {
            if !out.contains(&p.attr) {
                out.push(p.attr);
            }
        }
        out.truncate(n);
        out
    }
}

/// Edit distance between `a` and `b`, or None if it exceeds `max`.
fn levenshtein(a: &str, b: &str, max: usize) -> Option<usize> {
    let a: Vec<char> = a.chars().collect();
    let b: Vec<char> = b.chars().collect();
    if a.len().abs_diff(b.len()) > max {
        return None;
    }
    let mut prev: Vec<usize> = (0..=b.len()).collect();
    for (i, ca) in a.iter().enumerate() {
        let mut cur = vec![i + 1; b.len() + 1];
        for (j, cb) in b.iter().enumerate() {
            let cost = usize::from(ca != cb);
            cur[j + 1] = (prev[j] + cost).min(prev[j + 1] + 1).min(cur[j] + 1);
        }
        if cur.iter().min().copied().unwrap_or(0) > max {
            return None;
        }
        prev = cur;
    }
    let d = prev[b.len()];
    (d <= max).then_some(d)
}

fn score(row: &Row, query: &str, words: &[&str]) -> Option<u8> {
    let attr = row.0.to_lowercase();
    let pname = row.1.to_lowercase();
    if attr == query {
        return Some(0);
    }
    if pname == query {
        return Some(1);
    }
    if attr.starts_with(query) || pname.starts_with(query) {
        return Some(2);
    }
    if attr.contains(query) || pname.contains(query) {
        return Some(3);
    }
    let desc = row.3.to_lowercase();
    if words
        .iter()
        .all(|w| attr.contains(w) || pname.contains(w) || desc.contains(w))
    {
        return Some(4);
    }
    None
}

fn info(row: &Row) -> PackageInfo {
    PackageInfo {
        attr: row.0.clone(),
        pname: row.1.clone(),
        version: row.2.clone(),
        description: row.3.clone(),
        unfree: row.4,
        installed: false,
        license: None,
        license_accepted: false,
        local: false,
        origin: String::new(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const FIXTURE: &str = r#"[
        ["cowsay","cowsay","3.8.4","Program which generates ASCII pictures of a cow with a message",false],
        ["firefox","firefox","145.0","Web browser built from Firefox source tree",false],
        ["firefox-esr","firefox-esr","140.5esr","Web browser built from Firefox source tree",false],
        ["gimp","gimp","3.0.6","GNU Image Manipulation Program",false],
        ["python3Packages.cowsay","cowsay","6.1","Python cowsay clone",false],
        ["steam","steam","1.0","Digital distribution platform",true],
        ["vlc","vlc","3.0.21","Cross-platform media player and streaming server",false]
    ]"#;

    fn index() -> Index {
        Index::from_json(FIXTURE).unwrap()
    }

    fn attrs(results: Vec<PackageInfo>) -> Vec<String> {
        results.into_iter().map(|p| p.attr).collect()
    }

    #[test]
    fn exact_match_first_then_shorter_attrs() {
        assert_eq!(
            attrs(index().search("cowsay", 10)),
            ["cowsay", "python3Packages.cowsay"]
        );
        assert_eq!(
            attrs(index().search("firefox", 10)),
            ["firefox", "firefox-esr"]
        );
    }

    #[test]
    fn free_before_unfree_on_ties() {
        let idx = Index::from_json(
            r#"[["svp","svp","4.7","video player booster",true],
                ["mpv","mpv","0.40","video player",false]]"#,
        )
        .unwrap();
        assert_eq!(attrs(idx.search("video player", 10)), ["mpv", "svp"]);
    }

    #[test]
    fn description_words_match() {
        assert_eq!(attrs(index().search("image manipulation", 10)), ["gimp"]);
        assert_eq!(attrs(index().search("Media Player", 10)), ["vlc"]);
    }

    #[test]
    fn limit_and_empty_query() {
        assert_eq!(index().search("e", 2).len(), 2);
        assert!(index().search("   ", 10).is_empty());
    }

    #[test]
    fn lookup_and_suggest() {
        let idx = index();
        assert_eq!(idx.len(), 7);
        assert!(idx.get("steam").unwrap().unfree);
        assert!(idx.get("nope").is_none());
        assert_eq!(idx.suggest("firef", 1), ["firefox"]);
        assert_eq!(idx.suggest("cowsy", 1), ["cowsay"]);
        assert_eq!(idx.suggest("vcl", 1), ["vlc"]);
        assert!(idx.suggest("qqqqqqqq", 3).is_empty());
    }

    #[test]
    fn edit_distance() {
        assert_eq!(levenshtein("cowsy", "cowsay", 2), Some(1));
        assert_eq!(levenshtein("gimp", "gimp", 2), Some(0));
        assert_eq!(levenshtein("firef", "firefox", 2), Some(2));
        assert_eq!(levenshtein("abc", "xyzabc", 2), None);
    }
}
