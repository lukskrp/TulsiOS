# TulsiOS

A NixOS-based distribution that keeps NixOS's declarative, reproducible core
without making you write Nix every time you want to change something.

- **Ocimum Desktop**: a Cinnamon-based desktop (named after *Ocimum*, the basil genus).
- **Ocimum Software Center**: install and uninstall software from a GUI. Changes are
  declarative and you can roll them back.
- **Declarative browser extensions**: when you click "Add to Firefox/Chrome", TulsiOS
  installs the extension through Nix-managed browser policies instead.
- **Ocimum Assistant**: ask in plain language for a configuration change; review the
  diff; approve; done. System actions are also exposed as an MCP server.

> Status: **Phase 2: system daemon and `tulsi` CLI work in the dev VM.** Not a daily
> OS yet. See [docs/ROADMAP.md](docs/ROADMAP.md).

## Using it (inside TulsiOS)

```sh
tulsi install vlc gimp            # asks for your password, rebuilds, done
tulsi remove gimp
tulsi ext add firefox uBlock0@raymondhill.net
tulsi service enable docker
tulsi -n install obs-studio       # dry run: show what would change
tulsi history                     # every change is a git commit in /etc/nixos
tulsi undo                        # revert the latest change
```

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
| `crates/` | Rust workspace: `tulsi-state`, `tulsi-client`, `tulsi` CLI, `tulsid`, `tulsi-mcp`, GUI apps |
| `data/` | D-Bus and polkit policy files |
| `scripts/` | Developer scripts (`vm-e2e.sh`) |
| `browser/` | Ocimum Bridge WebExtension + native messaging host (Phase 4) |
| `desktop/` | Cinnamon fork for Ocimum Desktop (Phase 6) |
| `docs/` | Architecture, roadmap, setup, ADRs |

## License

TulsiOS's own code is MIT-licensed ([LICENSE](LICENSE)). The Cinnamon fork under
`desktop/` keeps its upstream GPL-2.0-or-later license.
