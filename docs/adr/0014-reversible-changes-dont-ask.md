# ADR 0014: Reversible changes don't ask

Status: accepted (2026-11-17)

## Context

Until now the Assistant's agent ran at Starah level 1 (Propose), and `org.tulsi.apply`
was class *admin*. So every package install and every configuration edit opened an
Agent Request window. That is a lot of friction for changes that NixOS already makes
safe. A package, a service switch or a browser extension lives in a NixOS generation, and
`tulsi undo`, an older boot entry or tulsid's automatic rollback of failed rebuilds undoes
it completely.

What a rollback does **not** undo is the real risk:
- the user's home files;
- accounts;
- disks, file systems and the boot loader;
- state under `/var/lib` and `system.stateVersion`;
- anything a script of the agent's choosing does when it runs.

We looked at Iron Jarvis (a local-first agent control plane; Apache-2.0 + Commons Clause,
so it is not used as code). Its core rule is worth borrowing as an idea: *the agent does
the setup itself, every change has an Undo, and it asks only about what cannot be undone*.
So is its practice of honest outcomes: what a reply says changed comes from the record,
not from what the model wrote.

## Decision

**Decide by reversibility, not by how risky something sounds.**

- **Two actions:**
  - `org.tulsi.apply` (class *routine*) is for changes a rollback fully undoes.
  - The new `org.tulsi.configure` (class *admin*) is for everything else.
  - For people, both have the same polkit defaults.
  - For agents at level 2 (Routine), Starah allows `apply` on its own and asks about
    `configure`.
- **Which action a change needs** (`tulsi_client::ops_action`, `config_action`):
  - **State operations:** packages, services, extensions and removing local packages use
    `apply`. Browser extensions alone still use `org.tulsi.extensions`.
  - **Adding a local package** (ADR 0013) uses `configure`: its code was written by an
    agent and ends up on the user's `PATH`.
  - **`configuration.nix` edits** are checked by `tulsi_state::unreversible_settings`.
    - It compares the old and new file line by line and places each changed line under
      its option path.
    - The edit is `apply` only if every changed setting is on a short allow-list:
      - `environment.systemPackages`;
      - fonts, time zone, locale and keyboard settings, host name;
      - `services.*/programs.*/hardware.*` `.enable` switches.
    - Even on the allow-list, a line never counts as reversible when:
      - it contains inline code: `''` scripts, `${…}`, path literals, `import`,
        `builtins`, `writeShellScript*`, `override*`, fetchers;
      - it is inside a multi-line string;
      - it touches `services.starah`, `services.openssh`, auto-login and a few other
        guards.
    - Anything the check cannot place counts as `configure`.
- **Undo needs what the change needed.**
  - tulsid writes the action into every commit as a `Tulsi-Action:` trailer.
  - `History` returns it.
  - `Undo` is authorized with it. Changes recorded before this ADR count as `configure`
    if they edited `configuration.nix`.
- **The Assistant's agent defaults to level 2.** The human still confirms it in Starah
  Setup.
- **Receipts instead of prompts:**
  - Every change tool of tulsi-mcp returns `structuredContent.receipt`, with:
    - `outcome`: `applied`, `nothing`, `rolled_back` or `rejected`;
    - `approved_via`;
    - `action`;
    - `changes`;
    - `commit`.
  - The Assistant shows a receipt line under the reply ("Changed: + package vlc · done on
    its own") with an **Undo** button. The button calls `undo_last_change` directly, and
    the model is told with the next message.
  - If a reply claims a change but no receipt shows one applied, a note says nothing was
    changed.
  - **Recent changes** opens the Software Center's History page
    (`ocimum-software-center --history`).

## Consequences

- At the default level, "install VLC" or "turn on printing" happens without a window,
  and the reply shows what changed with an Undo.
- Adding a user, changing the boot loader, editing a script, or installing a package the
  agent wrote itself still waits in the Agent Request window.
- **The check is textual and conservative, not an evaluator.**
  - It errs toward asking.
  - An allow-listed option set through an unusual construct (for example a `let` binding
    used later) asks.
  - It is a seatbelt on top of Starah's levels, not a sandbox. People who want to approve
    everything set the agent to level 1.
- Not carried over from Iron Jarvis: lowering an agent's powers after it reads untrusted
  content, per-level tool filtering and level ceilings. They add friction that rollback
  makes unnecessary. If agents ever get write access to home folders, an undo journal for
  file writes is the idea to revisit.
