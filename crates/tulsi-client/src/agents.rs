//! Coding-agent CLIs started by a person, and Starah (ADR 0026).
//!
//! An agent CLI a person starts in their terminal runs as that person. When it
//! runs `tulsi` (or `tulsi-mcp`), the environment variables it sets for its
//! commands give it away; the change is then made as the agent's own Starah
//! account instead (`starah run --agent NAME`), where the person's chosen level
//! decides, and Starah's Agent Request window asks them. This catches agents
//! that behave; one that hides its markers still runs as the person.

use std::collections::BTreeMap;
use std::sync::OnceLock;
use std::time::Duration;

use futures_util::StreamExt;
use serde::Deserialize;

/// Where Starah lists its agents (services.starah).
pub const STARAH_CONFIG: &str = "/etc/starah/config.json";
/// Set by Starah in every agent unit.
pub const STARAH_AGENT_ENV: &str = "STARAH_AGENT";

#[derive(Debug, Clone, Deserialize)]
pub struct AgentCli {
    pub name: String,
    pub title: String,
    pub attr: String,
    pub markers: BTreeMap<String, String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Table {
    pub fallback: String,
    pub generic: Vec<String>,
    pub agents: Vec<AgentCli>,
}

/// The agent CLIs TulsiOS knows (data/agent-clis.json).
pub fn table() -> &'static Table {
    static TABLE: OnceLock<Table> = OnceLock::new();
    TABLE.get_or_init(|| {
        serde_json::from_str(include_str!("../../../data/agent-clis.json"))
            .expect("data/agent-clis.json is valid")
    })
}

/// A name usable as a Starah agent (`[a-z][a-z0-9-]*`), or None.
fn clean(name: &str) -> Option<String> {
    let name = name.trim().to_ascii_lowercase();
    let ok = name.chars().next().is_some_and(|c| c.is_ascii_lowercase())
        && name
            .chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-');
    (ok && name.len() <= 32).then_some(name)
}

/// The agent CLI this process was started by, from the environment (`env`
/// looks a variable up). None for a person, and inside Starah already.
pub fn detect(env: impl Fn(&str) -> Option<String>) -> Option<String> {
    if env(STARAH_AGENT_ENV).is_some_and(|v| !v.is_empty()) {
        return None;
    }
    let t = table();
    for agent in &t.agents {
        let hit = agent.markers.iter().any(|(var, want)| {
            env(var).is_some_and(|v| !v.is_empty() && (want == "*" || v == *want))
        });
        if hit {
            return Some(agent.name.clone());
        }
    }
    for var in &t.generic {
        if let Some(value) = env(var).and_then(|v| clean(&v)) {
            // An agent's package name means the agent (AGENT=claude-code).
            let known = t.agents.iter().find(|a| a.name == value || a.attr == value);
            return Some(known.map_or(value, |a| a.name.clone()));
        }
    }
    None
}

/// The agent detected in this process's environment.
pub fn detect_here() -> Option<String> {
    detect(|var| std::env::var(var).ok())
}

/// The Starah agent to run as for `name`: itself if Starah declares it, else the
/// fallback agent, else None (Starah is not set up for agents here).
pub fn starah_agent(name: &str, declared: &[String]) -> Option<String> {
    if declared.iter().any(|d| d == name) {
        return Some(name.to_string());
    }
    let fallback = &table().fallback;
    declared
        .iter()
        .any(|d| d == fallback)
        .then(|| fallback.clone())
}

/// The agents Starah declares on this system (empty without Starah).
pub fn declared_agents() -> Vec<String> {
    #[derive(Deserialize)]
    struct Config {
        agents: BTreeMap<String, serde_json::Value>,
    }
    std::fs::read_to_string(STARAH_CONFIG)
        .ok()
        .and_then(|text| serde_json::from_str::<Config>(&text).ok())
        .map(|c| c.agents.into_keys().collect())
        .unwrap_or_default()
}

#[zbus::proxy(
    interface = "org.starah.Broker1",
    default_service = "org.starah.Broker1",
    default_path = "/org/starah/Broker1"
)]
trait StarahBroker {
    fn ask(&self, action: &str, description: &str) -> zbus::Result<(u64, String, String)>;
    #[zbus(signal)]
    fn decided(&self, id: u64, approved: bool, status: &str) -> zbus::Result<()>;
}

/// What Starah said about a change an agent described.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Decision {
    /// Approved: by the agent's level, or by the person (the text says which).
    Approved(&'static str),
    Rejected(String),
}

/// Asks Starah's broker about `action` (a polkit action id), described as JSON
/// `{"title", "reason", "changes", "diff"}`. Waits for the person when the
/// agent's level says so; `pending` is called once with the broker's message
/// when it does. An approval lets exactly this change through tulsid's polkit check.
pub async fn starah_ask(
    action: &str,
    description: &str,
    timeout: Duration,
    pending: impl FnOnce(&str),
) -> Decision {
    let asked = async {
        let conn = zbus::Connection::system().await?;
        let broker = StarahBrokerProxy::new(&conn).await?;
        // Subscribe before asking, so a quick answer is not missed.
        let mut decided = broker.receive_decided().await?;
        let (id, status, message) = broker.ask(action, description).await?;
        match status.as_str() {
            "approved" => {
                return Ok::<_, zbus::Error>(Decision::Approved("Starah (the agent's level)"))
            }
            "rejected" => return Ok(Decision::Rejected(format!("Starah: {message}"))),
            _ => pending(&message),
        }
        while let Some(signal) = decided.next().await {
            let a = signal.args()?;
            if a.id == id {
                return Ok(if a.approved {
                    Decision::Approved("Starah (the person)")
                } else {
                    Decision::Rejected(format!("the request was {} in Starah", a.status))
                });
            }
        }
        Ok(Decision::Rejected("lost the connection to Starah".into()))
    };
    match tokio::time::timeout(timeout, asked).await {
        Ok(Ok(decision)) => decision,
        Ok(Err(e)) => Decision::Rejected(format!("cannot ask Starah: {e}")),
        Err(_) => Decision::Rejected("nobody answered the request in Starah".into()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn env<'a>(vars: &'a [(&'a str, &'a str)]) -> impl Fn(&str) -> Option<String> + 'a {
        move |name| {
            vars.iter()
                .find(|(k, _)| *k == name)
                .map(|(_, v)| v.to_string())
        }
    }

    #[test]
    fn detects_agents_by_their_markers() {
        assert_eq!(
            detect(env(&[("CLAUDECODE", "1")])).as_deref(),
            Some("claude")
        );
        assert_eq!(
            detect(env(&[("CODEX_THREAD_ID", "abc")])).as_deref(),
            Some("codex")
        );
        assert_eq!(
            detect(env(&[("CRUSH", "1"), ("AGENT", "crush")])).as_deref(),
            Some("crush")
        );
        assert_eq!(
            detect(env(&[("TULSI_AGENT", "OpenCode")])).as_deref(),
            Some("opencode")
        );
        assert_eq!(
            detect(env(&[("AGENT", "claude-code")])).as_deref(),
            Some("claude")
        );
        assert_eq!(
            detect(env(&[("AI_AGENT", "newbot")])).as_deref(),
            Some("newbot")
        );
        // A person, a marker with the wrong value, a name that isn't one.
        assert_eq!(detect(env(&[])), None);
        assert_eq!(detect(env(&[("CLAUDECODE", "0")])), None);
        assert_eq!(detect(env(&[("AGENT", "rm -rf /")])), None);
        // Already inside Starah: nothing to route.
        assert_eq!(
            detect(env(&[("CLAUDECODE", "1"), ("STARAH_AGENT", "claude")])),
            None
        );
    }

    #[test]
    fn routes_to_a_declared_agent_or_the_fallback() {
        let declared = vec![
            "assistant".to_string(),
            "claude".into(),
            "terminal-agent".into(),
        ];
        assert_eq!(starah_agent("claude", &declared).as_deref(), Some("claude"));
        assert_eq!(
            starah_agent("newbot", &declared).as_deref(),
            Some("terminal-agent")
        );
        assert_eq!(starah_agent("claude", &["assistant".to_string()]), None);
    }

    #[test]
    fn the_table_is_consistent() {
        let t = table();
        assert!(clean(&t.fallback).is_some());
        for a in &t.agents {
            assert_eq!(
                clean(&a.name).as_deref(),
                Some(a.name.as_str()),
                "{}",
                a.name
            );
        }
    }
}
