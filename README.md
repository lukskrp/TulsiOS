# TulsiOS

A NixOS-based distribution that keeps NixOS's declarative, reproducible core
without making you write Nix every time you want to change something.

- **Ocimum Desktop**: a Cinnamon-based desktop (named after *Ocimum*, the basil genus).
- **Ocimum Software Center**: install and uninstall software from a GUI. Changes are
  declarative and you can roll them back.
- **Declarative browser extensions**: install an extension from the Firefox or Chrome
  store as usual; TulsiOS tells you it will be installed declaratively and moves it into
  Nix-managed browser policy.
- **Ocimum Assistant**: ask in plain language for a configuration change; review the
  diff; approve; done. System actions are also exposed as an MCP server.

> Status: **Phase 5b: Software Center, Assistant, `tulsi` CLI, system daemon, automatic
> declarative browser extensions and the `tulsi-mcp` agent interface work in the dev VM;
> GTK3-O is grafted system-wide.** Not a daily OS yet. See [docs/ROADMAP.md](docs/ROADMAP.md).

## Using it (inside TulsiOS)

Open **Software Center** from the menu: search, click Install or Remove, confirm, and
undo from the History tab or the bar that appears after a change. Or in a terminal:

```sh
tulsi search video player         # search 130k+ nixpkgs packages
tulsi install vlc gimp            # asks for your password, rebuilds, done
tulsi remove gimp
tulsi ext add firefox uBlock0@raymondhill.net
tulsi service enable docker
tulsi -n install obs-studio       # dry run: show what would change
tulsi history                     # every change is a git commit in /etc/nixos
tulsi undo                        # revert the latest change
```

### Let an AI agent do it

```sh
claude mcp add tulsi -- tulsi-mcp     # Claude Code; any MCP client works
```

Then ask: *"install a lightweight video player and enable Bluetooth"*. The agent plans
the change, you approve it in a dialog that shows exactly what changes, and TulsiOS
applies it. See [docs/MCP.md](docs/MCP.md).

Or use the built-in **Assistant** (menu → Assistant): the same thing in a chat window,
using Claude with your API key. See [docs/ASSISTANT.md](docs/ASSISTANT.md).

## How it works (one paragraph)

Tools never write Nix code. They edit a single JSON file,
[`state.json`](state/example.json) (schema: [`state/schema.json`](state/schema.json)).
The `tulsi.state` NixOS module turns that file into system config. Every change is
a normal `nixos-rebuild`, which creates a new generation you can roll back to. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quick start (developers)

Requires Nix with flakes on Linux (WSL2 works, see [docs/DEV-SETUP.md](docs/DEV-SETUP.md)).

```sh
nix develop                      # Rust + Nix tooling
cargo test                       # state contract tests
nix flake check                  # builds packages, evaluates the VM, runs NixOS tests
nix build .#nixosConfigurations.tulsi-vm.config.system.build.vm
./result/bin/run-tulsi-vm-vm     # boots the dev VM (user/password: tulsi/tulsi)
scripts/vm-e2e.sh                # headless VM: real `tulsi install` + `tulsi undo`
```

Without a VM, tulsid also runs on a session bus for quick experiments:
`tulsid --session --config my.json` with `"polkit": false`, then `TULSI_BUS=session tulsi …`.

## Layout

| Path | What |
|---|---|
| `flake.nix` | Entry point: overlay, NixOS modules, packages, dev VM, checks |
| `nix/modules/` | `tulsi.state`, `tulsi.daemon`, `tulsi.browserExtensions`, `ocimum.*` |
| `nix/hosts/` | `vm` (dev VM), `iso` (installer, later) |
| `nix/tests/` | NixOS VM tests |
| `state/` | State file schema and example |
| `crates/` | Rust workspace: `tulsi-state`, `tulsi-client`, `tulsi` CLI, `tulsid`, `tulsi-mcp` |
| `apps/` | GTK 3 GUI apps in Python: `ocimum-software-center`, `ocimum-assistant` |
| `nix/packages/` | `tulsi-tools`, `gtk3-o` (Ocimum GTK 3 fork, grafted system-wide), package index, apps |
| `data/` | D-Bus and polkit policy files |
| `scripts/` | Developer scripts (`vm-e2e.sh`) |
| `browser/` | Ocimum Bridge WebExtension + native messaging host (Phase 4) |
| `desktop/` | Cinnamon fork for Ocimum Desktop (Phase 6) |
| `docs/` | Architecture, roadmap, setup, ADRs |

## License

TulsiOS's own code is MIT-licensed ([LICENSE](LICENSE)). The Cinnamon fork under
`desktop/` keeps its upstream GPL-2.0-or-later license, and GTK3-O keeps GTK's
LGPL-2.1-or-later.
