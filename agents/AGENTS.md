<!-- TulsiOS links this file into each coding agent's global instructions (ADR 0022),
     only where you have none of your own. Edit your own copy freely: TulsiOS never
     overwrites a file it did not link. -->

# You are on TulsiOS

TulsiOS is a NixOS-based Linux distribution. The whole system is declared in
`/etc/nixos` and changed by the `tulsi` command (or the TulsiOS MCP server),
which records every change so it can be undone.

- **Never** edit `/etc/nixos`, run `nixos-rebuild`, `nix-env -i` or `nix profile
  install` to change the system. Use `tulsi install`, `tulsi remove`,
  `tulsi service enable|disable`, and `tulsi undo`. Each asks the person for
  authorization (or Starah, at the level they gave you).
- To look things up: `tulsi search WORDS`, `tulsi status`, `tulsi history`.
- Software that has no TulsiOS package: `tulsi recipe plan FILE`, then
  `tulsi recipe build FILE`, then `tulsi recipe install RESULT.json`.
- The desktop's colours and background: `tulsi-theme` (per person, no rebuild).
- Installed skills explain more: `tulsios` (the system), `tulsios-make-theme`,
  `tulsios-diagnose-crash`.

Report what actually happened: each change prints a receipt; say what it says.
