---
name: tulsios
description: >
  REQUIRED whenever you change or inspect a TulsiOS system for the person using it:
  installing or removing software, trying a program once (nix run / nix shell), a
  project's toolchain, turning services on or off, any other NixOS setting (Docker,
  Podman, virtual machines, user groups, firewall ports, NVIDIA and other drivers,
  Steam, kernel options, unfree software), undoing a change, upgrades, browser
  extensions, downloaded software with no package (Recipes, AppImages), pip / npm /
  cargo, the desktop (Ocimum, SonicDE, dwm), themes, AI agents and local models.
  Also whenever you are tempted to edit /etc/nixos, run nixos-rebuild, nix-env,
  nix profile, apt, curl | sh or sudo to install something.
---

# TulsiOS

TulsiOS is NixOS with a managed, recorded state. The whole system is declared in
`/etc/nixos`, a git-tracked flake, and changed by `tulsid` (a system service) on
request from the `tulsi` command, the Software Center, the Assistant or the
TulsiOS MCP server. Each change is a git commit plus a NixOS generation: it can be
undone, and a rebuild that fails is rolled back on its own.

| Path | What it is |
| --- | --- |
| `/etc/nixos/tulsi/state.json` | What `tulsi` manages: packages, services switched on/off, browser extensions, accepted licences, local packages |
| `/etc/nixos/configuration.nix` | The machine's own NixOS settings: users, desktop, hardware, everything else |
| `/etc/nixos/tulsi/pkgs/NAME/` | Packages made on this computer from downloads (Recipes) |
| `/etc/nixos/flake.nix`, `flake.lock` | Which TulsiOS release the machine follows |

## Rules

1. **Change the system only through `tulsi`** (or tulsi-mcp's tools, if you have
   them). Never write files in `/etc/nixos` yourself, and never run
   `nixos-rebuild`, `nix-env -i`, `nix profile install`, `sudo`, `curl … | sh`
   installers or mise to install or configure: they bypass the record and undo.
2. **Pick the smallest scope** (next section): a program needed once doesn't
   belong in the system.
3. **Dry-run first** when unsure: `tulsi -n …` shows what would change.
4. **Explain, then change.** Say what will change before you apply it, and
   whether it will ask the person.
5. **Report from the output.** Each change prints what it did. Rebuilds take
   minutes: wait for `Done:` or the error.

## Pick the right tool

| The person wants… | Do |
| --- | --- |
| to run a program once, or try it | `nix run nixpkgs#ATTR -- ARGS`, or `nix shell nixpkgs#ATTR nixpkgs#ATTR2` (gone when the shell closes) |
| a project's toolchain (compilers, linters, SDKs) | a dev shell in the project (below), or the language's project-local tool (a Python venv, `npm install` without `-g`, cargo in the project) |
| a program installed for good | `tulsi search WORDS`, then `tulsi install ATTR` |
| a service | `tulsi service enable NAME` (only `services.NAME.enable`) |
| any other setting: Docker, groups, firewall, drivers, Steam, kernel, unfree | `tulsi config` (below) |
| software that isn't in nixpkgs: a download, an AppImage, a .deb | a Recipe (below) |
| a browser extension | `tulsi ext add firefox|chromium ID` |
| colours and background | `tulsi-theme` (per person, no rebuild) |

`nixpkgs#` is TulsiOS' own pinned package set (the system's nix registry), so
`nix run nixpkgs#X` gives the build `tulsi install X` would, from the cache.
Attribute names are what `tulsi search` prints (`vlc`, `python3Packages.requests`).

A dev shell: `flake.nix` in the project, then `nix develop`. Add the file to git
first; flakes only see tracked files.

```nix
{
  inputs.nixpkgs.url = "nixpkgs";  # the system's pinned nixpkgs
  outputs = { nixpkgs, ... }:
    let pkgs = nixpkgs.legacyPackages.x86_64-linux;
    in {
      devShells.x86_64-linux.default = pkgs.mkShell {
        packages = [ pkgs.nodejs_22 pkgs.python3 pkgs.gcc ];
      };
    };
}
```

## Commands

| Task | Command |
| --- | --- |
| Find a package | `tulsi search WORDS` (installed ones marked `*`, `[unfree]` shown) |
| Another distro's name for it | `tulsi match --tool apt python3-requests` (`--tool` right after `match`) |
| Install / remove | `tulsi install ATTR...`, `tulsi remove ATTR...` (alias `uninstall`; removes packages a Recipe made too) |
| Services | `tulsi service enable NAME`, `tulsi service disable NAME` |
| Other settings | `tulsi config show`, `tulsi config diff FILE`, `tulsi config apply FILE --summary TEXT` |
| Browser extensions | `tulsi ext add|remove firefox|chromium ID` (chrome and brave mean chromium) |
| What is managed | `tulsi status` (packages, extensions, services) |
| What changed | `tulsi history [N]`: `ID  DATE  SUMMARY  (user)` or `(agent NAME)` |
| Undo | `tulsi undo` (latest), `tulsi undo ID` (one earlier change; later ones stay), `tulsi -n undo ID` (preview). Alias `rollback` |
| Upgrade TulsiOS | `tulsi upgrade --check`, then `tulsi upgrade` |
| What a download is | `tulsi inspect FILE` (JSON) |
| Keep a Recipe's download | `tulsi keep-source NAME on|off` |
| Version | `tulsi version` |

Options go anywhere on the line: `-n` (dry run), `-q` (hide rebuild output).

## Other settings: `tulsi config`

`tulsi service enable` only switches `services.NAME.enable`. Everything else is a
line in `configuration.nix`, changed like this:

```sh
tulsi config show > /tmp/configuration.nix      # the current file
# edit /tmp/configuration.nix: add lines inside the outer { … }
tulsi config diff /tmp/configuration.nix         # syntax check, the diff, who approves
tulsi config apply /tmp/configuration.nix --summary "Docker for alice"
```

Keep the rest of the file as it is and add to it. If the rebuild fails it is
rolled back and the error's last lines say why; `tulsi undo` takes back an edit
that worked.

**Groups:** each person already has a block `users.users."NAME" = { … extraGroups
= [ "networkmanager" "wheel" … ]; };`. Add the group to that list. A second
`extraGroups` line for the same person is an error ("already defined").

| Want | Change |
| --- | --- |
| Docker | `virtualisation.docker.enable = true;` and `"docker"` in the person's `extraGroups` (they log out and in after) |
| Podman | `virtualisation.podman.enable = true;` |
| Virtual machines | `virtualisation.libvirtd.enable = true;` `programs.virt-manager.enable = true;` and `"libvirtd"` in `extraGroups` |
| Open a firewall port | `networking.firewall.allowedTCPPorts = [ 8080 ];` |
| GPU or Wi-Fi drivers (NVIDIA, Intel/AMD video decoding, Broadcom) | Not by hand: use `tulsi-drivers` (below) |
| Steam | `programs.steam.enable = true;` `nixpkgs.config.allowUnfree = true;` |
| Kernel parameter | `boot.kernelParams = [ "quiet" ];` |
| Serial ports (Arduino…) | `"dialout"` in `extraGroups` |

`tulsi service enable docker` (or podman, libvirtd, steam…) refuses and points
here: those aren't `services.*` options.

**Drivers** (ADR 0029): `tulsi-drivers` detects the GPUs, Wi-Fi and processor and
writes its own block of `tulsi.drivers.*` settings in `configuration.nix`. Don't
write `hardware.nvidia.*` or `videoDrivers` yourself.

```sh
tulsi-drivers list            # devices, current drivers, choice ids (--json for data)
tulsi-drivers recommend       # what TulsiOS recommends for this computer
tulsi-drivers set nvidia      # a choice id from list, or `recommended`; --off EXTRA
tulsi-drivers status          # what is chosen, and a change waiting on a restart
```

- A driver change takes effect at the **next restart**, on trial: the person then
  keeps it (`tulsi-drivers keep`, or the prompt at login). Restarting without
  keeping it brings the drivers before back. You can't keep it for them: only the
  person at the screen knows whether it works.
- While a change is on trial, other system changes wait: tell the person to
  restart, or `tulsi-drivers undo`.
- NVIDIA's and Broadcom's drivers are unfree: `set` needs `--accept-unfree`, which
  also turns on unfree software for the whole system. Ask the person first.

- **Flatpak:** TulsiOS doesn't install Flatpaks; offer the nixpkgs package.
- **Unfree software:** the AI agents on the Software Center's AI Agents page
  install once the person accepts their licence there. Anything else unfree needs
  `nixpkgs.config.allowUnfree = true;` through `tulsi config`. Tell the person
  that this is what they are agreeing to.

## Approval

- **You are an agent, and Starah decides for you.** Set `TULSI_AGENT` to your
  name for every `tulsi` and `tulsi-mcp` command (`export TULSI_AGENT=claude`,
  or `opencode`, `codex`…). Claude Code, Codex, Gemini CLI, Qwen Code, Crush and
  Goose are recognised without it.
  - Your changes are then made as your own Starah account (`starah-NAME`), at
    the level the person chose for you.
  - Routine changes go through; the rest wait for the person in Starah's Agent
    Request window. `tulsi` says so and waits up to 15 minutes. Tell the person
    to look there.
  - Never unset these variables, or run `tulsi` some other way, to get around
    Starah. Agents TulsiOS doesn't know run as `terminal-agent`.
  - The person may also have their own **rules** (`/etc/starah/rules.rhai`, a
    Rhai script) that allow, ask or deny particular things, such as "no system
    changes at night". If you are refused with "your rules…", that is their
    choice. Don't try to edit the rules; tell them, and they can change them
    with Agent Privileges › Edit Rules… or `starah rules edit`.
- **You may already be your own account.** Agent CLIs installed through TulsiOS
  start under Starah: you run as `starah-NAME` (check with `id -un`).
  - You see only the folder the person started you in. Files you write there
    are theirs.
  - Your home is your own (logins, settings), not theirs.
  - Their SSH keys, `~/.gitconfig` and other projects aren't there, so
    `git push` and signed commits fail.
  - If they need that, tell them: in Agent Privileges they can let you use
    their whole home folder. Never work around it.
  - The person's own explanation of all this: `tulsi-wiki ai-agents` (the
    TulsiOS Wiki, offline). Point them there.
- **Routine or asks.** These are routine:
  - packages, services and extensions;
  - config edits that only touch `environment.systemPackages`, fonts, time zone,
    locale, keyboard, host name or printer drivers;
  - a `services|programs|hardware.X.enable` switch.

  Anything else in `configuration.nix` always asks: Docker, groups, firewall,
  kernel, boot, accounts, nix-ld, and code such as `''`, `${` or `import`.
  `tulsi config diff` prints which one an edit is.
- **Refused** (`tulsi: NotAuthorized: …`): the person (or your level) said no.
  Don't retry unasked.
- **Licences are the person's.** An agent can never accept one; the person does
  it in the Software Center.
- **Other errors:**
  - `Busy`: another change is running; wait and retry.
  - `Invalid`: the message says what is wrong.
  - `NotFound`.
  - `Failed`: the rebuild failed and was rolled back; read the lines it printed.
  - `tulsid is not running`.

## Software that isn't in nixpkgs (Recipes)

1. Try `tulsi search` and `tulsi match` first: a package is always better.
2. `tulsi inspect FILE` says what a download is. `tulsi recipe plan FILE` picks a
   recipe (tarball, .deb, AppImage, script, binary) and suggests answers (JSON).
3. `tulsi recipe build FILE [--name N --version V --program P --description D
   --free|--unfree --menu|--no-menu]` builds it in Nix's sandbox and tries it.
   Save the printed JSON (stdout) as `result.json`; the log is on stderr.
4. `tulsi recipe install result.json` installs it (asks the person).
5. **If the build fails:**
   - The draft is in `~/.local/share/tulsi/recipes/NAME/` (`package.nix`,
     `recipe.json`, `build.log`). Fix `package.nix`, then run
     `tulsi recipe build-draft DIR`.
   - `tulsi recipe check FILE` lists what TulsiOS refuses in a package.nix.
   - People can open the draft in the Nix Editor (`ocimum-nix-editor --draft DIR`).
   - Stop after a few failed attempts and explain.

Downloaded Linux binaries don't run as they are (NixOS has no `/usr/lib`); they
need a Recipe. The person's own tool for this is `tulsi-adopt --file|--url`,
"Install the TulsiOS Way". The Software Center's "Install from a File or Link…"
opens the same window.

## pip, npm, cargo and other package managers

- **Outside a project,** `pip install`, `npm install -g`, `cargo install`,
  `gem install`, `go install` and `flatpak install` open "Install the TulsiOS
  Way", which offers the nixpkgs package.
- **Inside a virtualenv or a project** the real tools run as usual, and the
  project's dependencies stay in the project.
- **`apt`, `dnf`, `pacman`, `zypper`, `snap` and `brew` don't exist** on TulsiOS.
  Use `tulsi match --tool apt NAME` to find the package.

## Undo and history

- `tulsi history` lists changes newest first, each by `(user)` or `(agent NAME)`.
- `tulsi undo ID` takes back one change and keeps everything since. It is refused
  if a later change edited the same lines; say which to undo first.
- Undoing needs the same approval the change needed.
- `git -C /etc/nixos log` is the full record, with `Tulsi-By:` and `Tulsi-Action:`
  lines.

## The person's files

`tulsi undo` covers the system, not files in home folders. So:
- **Delete with the trash,** never `rm -rf` on the person's files:
  `trash-put PATH` or `gio trash PATH`. The trash empties itself after 30 days.
- **File history,** if the person turned it on (`tulsi-file-history snapshots`
  lists snapshots; otherwise it says it is off):
  - `tulsi-file-history list PATH` shows earlier versions;
  - `tulsi-file-history restore PATH [--from N] [--copy]` brings one back (what
    is there now goes to the trash first);
  - `tulsi-file-history free --keep N` frees space by deleting older snapshots.
    Ask the person first: it can't be undone.
- **Turning the history on** is the person's choice: `tulsi-welcome`, or
  `tulsi-welcome --turn-on-history` (asks them; needs btrfs).
- **Disk space:** old system versions and unused store paths are removed weekly
  (`tulsi-cleanup`, as root, does it at once).

## Upgrades

Installed machines follow TulsiOS' release branch. `tulsi upgrade --check` says
whether a newer release is out. `tulsi upgrade` moves to it, can be undone like
any change, and needs a restart to finish. The desktop announces new releases.

## The desktop

- **Ocimum Desktop** (a Cinnamon fork), **SonicDE** (a KDE Plasma 6 fork on X11)
  and **dwm** share the XLibre display server and the Ocimum Greeter. Which one
  starts is `tulsi.desktop.session` in `configuration.nix`.
- **Themes** are per person, applied at once, no rebuild: `tulsi-theme list`,
  `tulsi-theme set SLUG`, `tulsi-theme undo`. The Themes app does the same.
  Making one: the `tulsios-make-theme` skill.
- **The person's own tools** for the same changes are the Software Center and the
  Assistant (Super+A). Suggest them to people who prefer windows to terminals.
- **AI agents and local models:**
  - The Software Center's AI Agents page (`ocimum-software-center --page ai`)
    lists agent CLIs and local runners.
  - `tulsi-ai-check` (`--json` for data) says which model sizes this computer can
    run and which Ollama package suits its graphics card.
  - Install them with `tulsi install ATTR`, never with curl scripts, npm -g, pip
    or mise.

## With the TulsiOS MCP server

If your client has tulsi-mcp connected, use its tools instead of the shell. To
connect it: `claude mcp add tulsi -- tulsi-mcp`; any MCP client can run
`tulsi-mcp`. The tools do the same things, and the person approves in a dialog:

- Packages, services, extensions: `search_packages`, `package_info`, `get_state`,
  `plan_change`, `apply_change`.
- Settings: `read_configuration`, `propose_configuration_edit`,
  `apply_configuration_edit` (the complete new file each time).
- History: `history`, `undo_last_change`, `undo_change`.
- Downloads: `fetch_source`, `build_package`, `try_package`,
  `propose_local_package`.
- Themes: `list_themes`, `set_theme`, `undo_theme`.
- Drivers: `list_drivers` (read only; change them with `tulsi-drivers set`).

Report what each result's receipt says happened.

## Looking around (always fine)

Reading never needs approval:
- `/etc/nixos/` (all of it), `/run/current-system`, and
  `/run/current-system/sw/share/tulsi/themes/`;
- `tulsi status`, `tulsi history`, `tulsi config show`;
- the logs: `journalctl -u tulsid` (what each change did) and
  `journalctl --user -b` (the desktop session).

Only changing goes through `tulsi`.
