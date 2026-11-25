# ADR 0022: Agent skills

Status: accepted (2026-11-25).

## Context

People run coding-agent CLIs (Claude Code, Codex, Gemini CLI, OpenCode, …) on
TulsiOS, packaged as ordinary software (ADR 0012). Out of the box those agents
know NixOS at best, and reach for `nixos-rebuild`, `nix-env -i` or edits to
`/etc/nixos`, which bypass `tulsi`'s recorded, undoable, authorized changes.
Omarchy (github.com/omacom/omarchy, MIT) solves the same problem for its
desktop with Agent Skills (`SKILL.md`) and one shared `AGENTS.md`, linked into
every agent CLI's folders (`omarchy-agent-skills-link`).

## Decision

- **TulsiOS ships skills** in `agents/skills/`, in the Agent Skills format:
  - `tulsios`: how to change and inspect a TulsiOS system (the `tulsi`
    commands, Recipes, undo, the desktops, themes), and the rule that changes
    go through `tulsi` or tulsi-mcp, never `/etc/nixos` directly;
  - `tulsios-make-theme`: making a palette theme (ADR 0021), with licensed,
    credited backgrounds only;
  - `tulsios-diagnose-crash`: core dumps, the journal, and `tulsi history` /
    `tulsi undo` to take back a change that caused a crash.
- **One `agents/AGENTS.md`** with the same rules in short.
- **`tulsi.agentSkills`** (on with any TulsiOS desktop) installs them at
  `/etc/tulsi/agents`, and a user unit at login (`tulsi-agent-skills-link`,
  also a command) links:
  - each skill into `~/.agents/skills`, and into `~/.claude/skills`,
    `~/.codex/skills`, `~/.gemini/config/skills`, `~/.pi/agent/skills` for
    agents that have been used (their folder exists);
  - `AGENTS.md` into `~/.agents/AGENTS.md`, `~/.claude/CLAUDE.md`,
    `~/.codex/AGENTS.md`, `~/.gemini/GEMINI.md`, OpenCode's and Qwen's, the
    same way.
- **A person's files always win:** only paths that don't exist, or that are
  links into `/etc/tulsi/agents`, are ever written. A skill or instruction file
  of their own with the same name stays.

## Consequences

- Any coding agent a person installs learns the TulsiOS way on their next
  login, and its changes stay recorded, authorized and undoable.
- The links point at `/etc/tulsi/agents`, so skills update with the system;
  skills TulsiOS stops shipping lose their links at the next login.
- An agent first used after login is linked at the next login (or by running
  `tulsi-agent-skills-link`).
- The Ocimum Assistant keeps its own instructions (tulsi-mcp's), which say the
  same.

## Addendum (2026-11-25): what the `tulsios` skill covers

An audit against the code found the skill wrong about state.json's path and
Starah's role, and silent about every change beyond packages. The skill now
covers:

- **The scope to pick:**
  - `nix run` / `nix shell nixpkgs#X` for a program needed once;
  - a project dev shell or project-local tools for a toolchain;
  - `tulsi install` for keeps;
  - `tulsi service` for `services.*`;
  - `tulsi config` for any other setting;
  - Recipes for downloads.

  `nixpkgs#` is the system's pinned nixpkgs: NixOS sets the registry from
  the flake that built the system.
- **`tulsi config show|diff|apply`**, new in the CLI. It is the same path as
  tulsi-mcp's configuration tools, so terminal agents without MCP can change
  Docker, groups, the firewall, drivers and kernel options, recorded and
  undoable. `tulsi config diff` says whether an edit is routine or always asks.
- **Approval:** who is asked (the person, or Starah for `starah-*` agents),
  refusals and Starah's retry-after-approval, licences, and the error kinds.
- **The rest:** undo of earlier changes, the pip/npm/cargo shims, upgrades
  (restart to finish), the full tulsi-mcp tool list, and where the logs are.

Two CLI bugs went with it:
- **`tulsi remove` of a Recipe-built package** now removes the local package
  (tulsid resolves the op, so the Software Center and tulsi-mcp get it too).
- **`tulsi service enable docker`** and other `virtualisation.*`/`programs.*`
  names now refuse and point at `tulsi config`, instead of failing at the
  rebuild.

`checks.agent-skills-commands` fails if a skill names a `tulsi` command the
CLI doesn't have.
