# ADR 0030: Your own rules for AI agents

Status: accepted (2026-11-26). Implemented in Starah.

## Context

Starah decides with a fixed table: an agent's level (0–4) against an action's class
(observe, routine, admin, sensitive, forbidden). That covers most people. It can't say
things like:

- "Codex may install packages on its own, but nothing else without asking";
- "no agent administers the system at night";
- "Claude never touches services".

The person asked for levels they can program, edited in a text editor with
administrator rights, and reachable from Starah's window.

## Decision

**Rules are a Rhai script**, `/var/lib/starah/rules.rhai`; `/etc/starah/rules.rhai`
links to it. Starah's DESIGN.md has the details.

- **The script:** it defines `decide(req)`, which answers `"allow"`, `"ask"`, `"deny"`
  or `"default"` (the level decides).
  - `req` has the agent, its level, the action and its class, the detail, what a
    cooperating agent described (title, reason, changes), the local hour and weekday,
    and the table's verdict.
- **Rhai:** a small language made for embedding in Rust. It has no access to files,
  the network or processes, and it limits operations. JavaScript (polkit's language)
  would have needed a far larger engine in starahd, and a declarative list couldn't
  express "all changes are package installs".
- **Floors:**
  - the forbidden class (Starah itself, accounts, polkit and sudo rules) stays denied;
  - a failing or runaway script counts as the stricter of the table and "ask";
  - agents can't read or change the rules.
- **Editing, checked like visudo:** `starah rules edit` copies the rules and opens
  `$EDITOR` (Fresh, ADR 0031). starahd compiles the result and tries it on every
  agent.
  - A broken script is never installed; it reopens.
  - Installing asks for the administrator password and keeps the version before
    (`starah rules undo`).
- **Editing by hand also works:** `sudoedit /etc/starah/rules.rhai`. starahd reloads
  before the next decision. A broken file is refused, the last good rules stay, and the
  window says so.
- **In the window:** Agent Privileges has **Edit Rules…**, which opens `starah rules
  edit` in a terminal, and a line saying whether the rules are in use or have an error.
- **Seed:** a new system starts with commented examples that change nothing
  (`services.starah.rules.initial` can set others).
- **Audit:** every decision in the audit log carries the hash of the rules that made
  it, as do `set-rules`, `undo-rules` and `rules-error`.

## Consequences

- People can shape what agents do beyond five levels, without rebuilding the system.
- The rules live in `/var/lib/starah`, not in `/etc/nixos`, so `tulsi undo` and the
  Software Center's History don't cover them. They have their own history
  (`starah rules undo`, the last 20 versions) and audit entries.
- A person can write rules that allow more than any level would, for example sensitive
  actions on their own. That is their decision: the floors above still hold.

## Verification

- **starah-policy unit tests:** the example both commented and uncommented, syntax
  errors with their line, a wrong answer, runtime errors, an endless loop stopped, no
  `eval`, every request field, local time, the forbidden floor, failures that ask, and
  descriptions seen by the rules.
- **starahd tests:** seed, load, refuse a broken edit, install, undo, file mode.
- **Starah `checks.agents`:**
  - the seeded file;
  - agents refused;
  - a `starah rules edit` that denies services to a level-4 agent;
  - a broken edit refused;
  - a hand edit by root used at once, and a broken one keeping the last good rules;
  - undo, and the audit entries.
- **The session app's tests:** the terminal command and the status line.
