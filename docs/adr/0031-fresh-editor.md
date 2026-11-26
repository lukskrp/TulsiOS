# ADR 0031: Fresh is the terminal editor

Status: accepted (2026-11-26).

## Context

TulsiOS inherited NixOS's terminal editor, nano (`EDITOR=nano`). The person chose
[Fresh](https://getfresh.dev) instead.

- **What Fresh is:** a terminal editor written in Rust, under the GPL 3.
- **Keys:** the ones people know from desktop apps (Ctrl+S, Ctrl+Z, Ctrl+P for
  commands).
- **Also:** a mouse, menus, multiple cursors, and language servers.

The editor matters more now: `starah rules edit` (ADR 0030), `sudoedit`, `git commit`
and `crontab -e` all open it.

## Decision

- **tulsipkgs** has `fresh-editor` 0.5.9.
  - The wrapper's `--no-upgrade-check` turns off both the daily update check and the
    anonymous telemetry (they share the setting).
  - The package also installs its app-menu entry, icon and manual page.
- **`tulsi.editor`** (`nix/modules/editor.nix`, on by default):
  - installs Fresh;
  - sets `EDITOR` and `VISUAL` to `fresh`, above NixOS's `mkDefault "nano"`, as
    `programs.vim.defaultEditor` does;
  - turns off `programs.nano`, so nano isn't installed.
- **Double-clicked text files** still open the desktop's editor (xed on Ocimum, pinned
  as the `text/plain` default because Fresh's entry offers itself for text files too).
- **System files:** `sudoedit FILE`. It runs Fresh as the person and writes the file
  back as root. That avoids running the editor as root, where Fresh's own settings
  don't load (upstream issue 3511).

## Consequences

- People who prefer nano or vim install it (`tulsi install nano`) and set
  `environment.sessionVariables.EDITOR` through `tulsi config`, or set it for
  themselves.
- The live ISO's session gets Fresh too once it is rebuilt.

## Verification

- **`nix build .#fresh-editor`** in tulsipkgs, with its tests and `fresh --version`.
- **`checks.editor`:**
  - `EDITOR` and `VISUAL` are `fresh`;
  - nano is gone;
  - the app-menu entry is there;
  - `git commit` and `sudoedit` start the editor, and sudoedit starts it as the person
    on a copy of the file.
