# ADR 0028: Agent CLIs run as their own Starah accounts

Status: accepted (2026-11-25). Completes ADR 0026's step 2.

## Context

ADR 0026 made the system changes of recognised agents go through Starah. But an
agent CLI started in a terminal still ran as the person, which left gaps:

- An agent that sets no marker (OpenCode, Antigravity, Aider, Copilot, Cursor,
  Amp), or one that hides its marker, was gated only by the person's password.
- Any agent could read and change every file in the person's home.

`starah run` gave agents their own account, but couldn't host an interactive
agent: it had no terminal, no access to the project, no API keys, and the wrong
directory.

## Decision

**Starah: `starah run --interactive`** (broker method `RunInteractive`).

- **Terminal:**
  - The client opens a pseudo-terminal and passes its name. starahd checks that
    the caller owns it, and systemd opens it for the agent's unit as its
    controlling terminal.
  - The client puts its own terminal in raw mode and relays keys, output and
    window size.
  - If the client goes away, starahd stops the agent.
- **Files:** a short root unit (`starahd --prepare-session`) checks that the
  current folder is the caller's, inside their home and not the home itself.
  It then mounts that folder with an **idmapped bind mount**, which the agent's
  unit binds back at the same path.
  - The agent works on the files as if they were its own, and they stay the
    person's on disk. The spike confirmed this on the kernel and util-linux
    TulsiOS ships.
  - The rest of `/home` is an empty tmpfs to the agent.
  - `--end-session` unmounts the folder when the session ends.
- **Home:** each agent has a home per person
  (`/var/lib/starah-agents/NAME/home/PERSON`), for its logins and settings.
  `services.starah.agents.NAME.homeLinks` puts links there (TulsiOS' skills and
  AGENTS.md).
- **Environment:** only `TERM`, `COLORTERM`, `LANG`, `LC_*`, `TZ`, `NO_COLOR`
  and `*_API_KEY` / `*_BASE_URL` / `*_API_BASE` pass from the terminal.
- **The whole home, if the person says so.** Agent Privileges has, for each
  agent, "May use my whole home folder" (also `starah home AGENT on|off`).
  - It is off by default, needs the administrator password, is audited, and
    is per person.
  - When on, the agent gets the person's whole home through the same idmapped
    mount, with `HOME` set to it. That brings the person's logins, settings and
    SSH keys, so `git push` works.
  - The window says what it means. So does the TulsiOS Welcome window.

**TulsiOS: `tulsi.agentGating` wraps each agent CLI installed through TulsiOS**
(`claude`, `codex`, `gemini`, `qwen`, `crush`, `goose`, `opencode`, `aider`,
`copilot`, `amp`, `cursor-agent`, `agy`).

- **Started in a terminal,** the CLI runs under
  `starah run --interactive --agent NAME`.
- **With no terminal** (scripts, editors), it runs as the person with
  `TULSI_AGENT=NAME`, so its system changes still go through Starah
  (ADR 0026).
- **Each wrapped agent is declared to Starah** with its home links.

**Telling people.** The TulsiOS Wiki (`docs/wiki`, built into offline HTML
pages: the app menu's "TulsiOS Wiki", `tulsi-wiki PAGE`) explains it in "AI
agents and Starah": levels, what an agent sees, the whole-home switch, and, as a
warning, that **an agent installed outside TulsiOS runs as the person** with all
their files. The Welcome window and Starah's Agent Privileges window carry the
same warning and open that page.

## Consequences

- **What the person notices:**
  - each agent logs in once more, in its own home;
  - `git push`, signed commits and the person's other projects need "May use my
    whole home folder";
  - the agent can't be started in the home folder itself without it.
- **What stays open:**
  - an agent installed outside TulsiOS (npm, a downloaded binary) isn't
    wrapped. ADR 0026's markers remain its gate.
  - network access is unrestricted, as Starah documents.
- **Shared accounts:** two people using the same agent share its account, but
  each has a separate 0700 home in it.

## Verification

- **Starah, `checks.agents`** has three new interactive subtests:
  - **the project folder only:** the agent's own user on a terminal of the
    right size, in the project folder, with its own home and links; what it
    writes is the person's; the rest of the home is hidden; the mount is gone
    afterwards;
  - **the whole home:** refused unless allowed; with "whole home" on, it sees
    the home with `HOME` set to it, and the change is audited;
  - **when the terminal goes away,** the agent is stopped and cleaned up.
- **TulsiOS, `checks.agent-gating`:** `claude` (a stand-in), started in
  Alice's project from a terminal, runs as `starah-claude`, in that folder
  only, with TulsiOS' skills in its home. What it writes is Alice's.
