<!-- TulsiOS links this file into each coding agent's global instructions (ADR 0022),
     only where you have none of your own. Edit your own copy freely: TulsiOS never
     overwrites a file it did not link. -->

# You are on TulsiOS

TulsiOS is a NixOS-based Linux distribution. The whole system is declared in
`/etc/nixos` and changed by the `tulsi` command (or the TulsiOS MCP server), which
records every change so it can be undone.

- **Never** write to `/etc/nixos` yourself, or run `nixos-rebuild`, `nix-env -i`,
  `nix profile install`, `sudo`, `curl … | sh` installers or mise to change the
  system.
- **Use the smallest scope:**
  - a program needed once: `nix run nixpkgs#ATTR` or `nix shell nixpkgs#ATTR`;
  - a project's toolchain: a `flake.nix` dev shell (`nix develop`) or the
    project's own venv / npm / cargo;
  - installed for good: `tulsi search WORDS`, then `tulsi install ATTR`;
  - a service: `tulsi service enable NAME`;
  - any other setting (Docker, groups, firewall, drivers, kernel):
    `tulsi config show > FILE`, edit FILE, `tulsi config diff FILE`, then
    `tulsi config apply FILE --summary TEXT`.
- **Approval goes through Starah:** run `tulsi` and `tulsi-mcp` with
  `TULSI_AGENT=<your name>` set (e.g. `export TULSI_AGENT=opencode`). Your changes
  are then made as your own Starah account, at the level the person chose for
  you. What needs the person waits in Starah's Agent Request window. Never get
  around this. On `NotAuthorized`, don't retry unasked.
- **Undo:** `tulsi history`, `tulsi undo`, `tulsi undo ID` (one earlier change).
- **Software not in nixpkgs:** `tulsi recipe plan FILE`, then `tulsi recipe build
  FILE`, then `tulsi recipe install RESULT.json`.
- **Desktop colours and background:** `tulsi-theme` (per person, no rebuild).
- **The installed skills explain more:** `tulsios` (the system), `tulsios-make-theme`,
  `tulsios-diagnose-crash`.

Report what actually happened: each change prints what it did; say what it says.
