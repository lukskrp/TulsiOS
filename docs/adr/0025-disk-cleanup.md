# ADR 0025: Disk cleanup

Status: accepted (2026-11-25).

## Context

Every TulsiOS change, every undo and every upgrade is a NixOS generation.
Nothing removed them: there was no `nix.gc`, no store optimisation, no limit on
boot entries and no cap on the journal. NixOS already needs more disk than most
systems, because the store keeps every version side by side. So a TulsiOS
machine filled up a little more with each click.

Undo doesn't need old generations. tulsid undoes a change by rebuilding from
the git record in `/etc/nixos`, so only the boot menu's "older versions" use
them.

## Decision

`tulsi.cleanup` is on wherever tulsid is.

- **Weekly** (`tulsi-cleanup.timer`, catching up after downtime):
  - remove system generations older than `keepDays` (30);
  - always keep the newest `keepGenerations` (10), the current one and the
    booted one;
  - then `nix-store --gc`.

  It waits while a rebuild is running, and runs at idle priority.
- **Store optimisation:** `nix.settings.auto-optimise-store`, so identical
  files in the store are stored once.
- **Boot menu:** lists at most `keepGenerations` versions (systemd-boot and
  GRUB).
- **Journal:** capped at 1 GB.

All of these are `mkDefault`, so a person's `configuration.nix` can change them.

## Consequences

- Undo works as before, at any age.
- Rolling back from the boot menu reaches the last 10 versions, and any version
  from the last 30 days.
- A Recipe's kept download (ADR 0018) stays while the current system includes
  it. Once a package is removed, its download goes at the next cleanup that
  drops the last generation using it.
- `tulsi-cleanup` can be run by hand (as root) to free space at once.

## Verification

`checks.cleanup` makes 15 generations, 12 of them back-dated by 40 days, and
runs the cleanup. The 5 old ones outside the newest 10 go; the newest 10 and the
booted system stay. It also checks the journald and nix.conf settings and the
timer.
