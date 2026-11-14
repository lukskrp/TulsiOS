# ADR 0012: AI agent CLIs: fast-tracked updates and accepted licences

Status: accepted (2026-11-14)

## Context

People want current AI agent CLIs: Codex, Gemini CLI, opencode, Claude Code and others.
These ship new releases weekly or faster. Two questions:

1. **Updates.** nixpkgs already detects new releases: every package has an update script,
   and a bot opens pull requests with them. A release still reaches TulsiOS 1–7 days
   later, after review, Hydra and the daily tulsi-sync. Per-user tool managers such as
   mise or `npm -g` are faster, but they live outside TulsiOS's declarative state: no
   history, no Undo, no approval, and unpinned binaries that often need patching on
   NixOS. They also let an agent replace its own binary.
2. **Licences.** Several popular agent CLIs are proprietary: claude-code, amp-cli,
   cursor-cli, github-copilot-cli and crush. tulsid refused every unfree package unless
   the whole system allowed unfree software.

## Decision

**Updates: tulsipkgs fast-tracks free agent CLIs** (`ci/tulsi/agents.txt`: codex,
gemini-cli, opencode, aider-chat, goose-cli, qwen-code).
- Every 6 hours, `tulsi-agents.yml` runs each package's own nixpkgs update script, builds
  the new version and smoke-tests it (`--version`, `--help`).
- **When it passes:** the workflow opens or refreshes one pull request per agent. A person
  merges it after reading the changelog, and tulsi-build caches the new version on
  cache.skarptech.org.
- **When it fails:** the workflow opens an issue, the step that needs a person or an agent.
- **When nixpkgs catches up:** tulsi-sync resolves the resulting conflicts by taking
  upstream's files.

TulsiOS users get the new version with their normal system update. mise stays available
for developers' project toolchains; it is not how TulsiOS installs agents.

**Licences: a named allow-list, accepted by a person.**
- `tulsi.daemon.unfreeAgents` lists the proprietary agent CLIs. tulsid shows each one's
  licence, taken from the package's metadata.
- Installing one in the Software Center first asks the person to accept that licence.
  This records `acceptedLicenses` in state.json, through the new op `acceptLicense`.
  `tulsi.state` then allows exactly those packages through
  `nixpkgs.config.allowUnfreePredicate`.
- tulsid refuses `acceptLicense` from Starah agents (ADR 0011). An agent may install an
  agent CLI whose licence a person accepted, but never accept one itself.
- These binaries are not put on our public cache: machines download them from the
  vendor, pinned by hash.

## Consequences

- **Free agents** are hours behind their vendors, built and tested, and cached by
  TulsiOS. Updates still go through history, Undo and, for agents, Starah.
- **People step in** when a build breaks, a licence changes or a release looks wrong.
  Merging a pull request and reading the issue are the only routine tasks.
- **Configuration conflict:** a system configuration that sets its own
  `nixpkgs.config.allowUnfreePredicate` conflicts with accepted licences. Such machines
  should list the agents in their own predicate instead.
- **First real run:** gemini-cli 0.47.0 → 0.68.0 already fails to build (its npm
  dependencies changed). This is the "issue, then a person or agent fixes the recipe" case.
