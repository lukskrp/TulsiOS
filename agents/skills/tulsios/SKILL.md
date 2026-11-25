---
name: tulsios
description: >
  REQUIRED whenever you change or inspect a TulsiOS system for the person using it:
  installing or removing software, turning services on or off, undoing a change,
  upgrades, browser extensions, software with no TulsiOS package (Recipes), the
  desktop (Ocimum, SonicDE, dwm), themes, and finding out what is installed. Also
  when you are tempted to edit /etc/nixos, run nixos-rebuild, nix-env or nix profile.
---

# TulsiOS

TulsiOS is NixOS with a managed state. `/etc/nixos` is a git-tracked flake
whose `state.json` lists what the person installed; `tulsid` (a system
service) changes it, rebuilds, and records each change as a NixOS generation.
Every change can be undone, and a failed rebuild is rolled back on its own.

## Rules

1. **Change the system only through `tulsi`** (or the TulsiOS MCP server's
   tools, if you have them: `search_packages`, `plan_change`, `apply_change`,
   `undo_last_change`). Never edit `/etc/nixos` yourself, never run
   `nixos-rebuild`, `nix-env -i`, `nix profile install` or `sudo` to install.
2. **Every change asks for authorization**: a polkit prompt for the person, or
   Starah's broker for an agent. If they refuse, do not try again unasked.
3. **Dry-run first** when unsure: `tulsi -n install vlc` shows what would change.
4. **Say what happened, from the output.** Rebuilds take minutes; wait for them.

## Commands

| Task | Command |
| --- | --- |
| Find a package | `tulsi search WORDS` (installed ones marked `*`) |
| Install / remove | `tulsi install PKG...`, `tulsi remove PKG...` (nixpkgs attribute names, e.g. `python3Packages.requests`) |
| Another distro's package name | `tulsi match --tool apt python3-requests` |
| A service | `tulsi service enable NAME` (= `services.NAME.enable`) |
| Browser extension | `tulsi ext add firefox|chromium ID` |
| What changed | `tulsi history [N]`, `tulsi status` |
| Undo | `tulsi undo` (latest) or `tulsi undo ID` (from history) |
| Upgrade TulsiOS | `tulsi upgrade --check`, `tulsi upgrade` |
| What a download is | `tulsi inspect FILE` (JSON) |

## Software with no TulsiOS package (Recipes, ADR 0018)

1. `tulsi search` and `tulsi match` first: a package is always better.
2. `tulsi recipe plan FILE` picks a recipe and suggests answers (JSON).
3. `tulsi recipe build FILE [--name N --version V --program P --free|--unfree]`
   builds and tries it as the person; save the printed JSON as `result.json`.
4. `tulsi recipe install result.json` installs it (asks for authorization).
5. If a build fails, the Nix Editor (`ocimum-nix-editor --draft DIR`) opens the
   draft with nixd and the TulsiOS Nix guide; `tulsi recipe check FILE` lists
   what TulsiOS refuses in a package.nix.

## The desktop

- **Ocimum Desktop** (a Cinnamon fork), **SonicDE** (a KDE Plasma 6 fork on X11)
  and **dwm** share the XLibre display server and the Ocimum Greeter.
- **Themes** are per person, applied at once, no rebuild: `tulsi-theme list`,
  `tulsi-theme set SLUG`, `tulsi-theme undo`. The Themes app does the same.
  Making one: the `tulsios-make-theme` skill.
- The Software Center and the Assistant (Super+A) are the person's own tools for
  the same changes; suggest them to people who prefer windows to terminals.
- **AI agents and local models:** the Software Center's AI Agents page
  (`ocimum-software-center --page ai`) lists the agent CLIs and the local
  runners. `tulsi-ai-check` (or `tulsi-ai-check --json`) tells which model sizes
  this computer can run and which Ollama package suits its graphics card. Never
  install agents or runners with curl scripts, npm -g, pip or mise: use
  `tulsi install ATTR` so it can be undone.

## Reading is always fine

`/etc/nixos/flake.nix`, `/etc/nixos/state.json`, `/run/current-system`,
`/run/current-system/sw/share/tulsi/themes/` and the TulsiOS docs can be read
freely to understand the system. Only changing goes through `tulsi`.
