# ADR 0026: Coding agents in a terminal change the system through Starah

Status: accepted (2026-11-25), step 1. Step 2 (agents run as their own accounts
from the start) is in progress; see "Next".

## Context

Starah (ADR 0011) gives AI agents levels, from Observe to Delegate, by running
them as their own accounts (`starah-NAME`). It only covers agents started with
`starah run`. A coding agent a person opens in their terminal (Claude Code,
Codex, OpenCode, …) runs as that person. To polkit it *is* the person:

- its `tulsi install` or `tulsi config apply` asked only for the person's
  password;
- polkit remembered that approval for a few minutes (`auth_admin_keep`), so
  later changes could go through without asking;
- with `tulsi.daemon.wheelNoPassword`, nothing asked at all.

Starah and tulsid tell agents apart only by account, and a process running as
the person can't be told from the person reliably.

## Decision

Step 1, the part a well-behaved agent can't avoid:

- **Recognise agents by what they set.** Most agent CLIs set an environment
  variable for the commands they run. `data/agent-clis.json` lists the ones
  checked against each CLI's source:
  - `CLAUDECODE=1`, `CODEX_THREAD_ID`, `GEMINI_CLI=1`, `QWEN_CODE=1`,
    `CRUSH=1` and `GOOSE_TERMINAL=1`;
  - the generic `AGENT` / `AI_AGENT` names (Crush and Goose set them);
  - `TULSI_AGENT`, which the TulsiOS skill and AGENTS.md ask every agent to set.
- **`tulsi` re-runs an agent's change as the agent.** A system-changing command
  (install, remove, service, ext, keep-source, `config apply`, undo, upgrade,
  `recipe install`) started by a recognised agent runs again as
  `starah run --agent NAME -- tulsi …`. Files it reads are passed on stdin,
  because the agent's sandbox can't see them.
  - Inside Starah, `tulsi` asks Starah's broker before each change (the "ask"
    kind tulsi-mcp already uses). The agent's level answers, or the person in
    the Agent Request window.
  - History records the change as `Tulsi-By: starah-NAME`.
  - Dry runs and reading stay the person's.
- **`tulsi-mcp` does the same:** started by a recognised agent, in its default
  mode, it serves as `starah run --agent NAME -- tulsi-mcp --approval starah`,
  as the Assistant's does.
- **`tulsi.agentGating`** (on with Starah and tulsid) declares a Starah agent
  for each agent CLI installed through TulsiOS, plus `terminal-agent` for agents
  TulsiOS doesn't know. Each starts at level 1 (asks about every change). People
  set the levels in Starah Setup and Agent Privileges.
- **People's approvals aren't remembered.** `org.tulsi.apply`, `configure` and
  `upgrade` now use `auth_admin`, not `auth_admin_keep`, so an approval covers
  one change. Browser extensions keep `_keep`.
- **`wheelNoPassword` warns** that recognised agents are the only ones still
  gated.

## Consequences

- Agents that behave can't change the system behind the person's back. An
  agent that deliberately removes its variables still runs as the person. Its
  changes still need the person's password every time, but Starah's levels
  don't apply to it. Step 2 closes that.
- People type their password once per change in the Software Center too. That
  is the cost of not letting a terminal agent ride on an earlier approval.
- An agent first used from a package installed outside TulsiOS is gated as
  `terminal-agent` until it is installed through TulsiOS.

## Next (step 2)

- **Agent CLIs start under Starah:** `claude`, `codex` and the rest are
  wrapped to start through `starah run` as their own accounts, so even their
  file access is the agent's.
- **Starah needs an interactive mode first:**
  - a real terminal;
  - the person's current project directory, read-write, with files staying
    theirs;
  - an environment allow-list (API keys);
  - a per-person agent home.

## Verification

- **`checks.agent-gating`:**
  - with `CLAUDECODE=1`, `tulsi install` waits for the person in Starah, is
    made after approval, and is recorded as `starah-claude`;
  - a rejection changes nothing;
  - an unknown agent (`AGENT=newbot`) runs as `terminal-agent`, and
    `tulsi config apply FILE` reaches it through stdin;
  - dry runs stay the person's;
  - `tulsi-mcp` started with the marker serves as `starah-claude`;
  - the polkit policy no longer remembers approvals.
- **cargo tests** cover marker detection, routing and which commands go through
  Starah.
