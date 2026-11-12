# ADR 0008: tulsipkgs, a hard fork of nixpkgs, and Ocimum Desktop as a hard fork of Cinnamon

Status: accepted (2026-11-12). Changes where GTK3-O comes from (ADR 0006: now
tulsipkgs, not a flake input); the graft itself stands.

## Context
Cinnamon is a version-locked suite: cinnamon, muffin, cinnamon-desktop,
cinnamon-session, cinnamon-settings-daemon, nemo, xapp and the rest only work
together at matching releases. Ocimum Desktop wants the newest Cinnamon (6.8), while
nixpkgs pins the whole suite at 6.6. Overriding the suite from the TulsiOS flake would
work, but every TulsiOS user would compile it, there would be no place for other
TulsiOS-owned software (GTK3-O, OTK, the app suite), and nothing would be cached.

Ocimum Desktop is not meant to follow Cinnamon's direction. Cinnamon is the base;
from here on Ocimum goes its own way.

## Decision
- **tulsipkgs** (`github.com/lukskrp/tulsipkgs`) is a hard fork of nixpkgs. Branch
  `tulsi-unstable` = upstream `nixos-unstable` + TulsiOS commits. The `tulsi-sync`
  workflow merges upstream daily and pushes only if the merged tree builds; conflicts
  open an issue. TulsiOS's flake input `nixpkgs` points at `tulsi-unstable`.
- **Affordability rule** (`TULSI.md` in tulsipkgs): change only what TulsiOS owns
  (Ocimum suite, GTK3-O, OTK) and never edit widely used base packages in place.
  Everything else keeps the exact upstream derivation, so it still comes from
  cache.nixos.org.
- `pkgs/top-level/tulsi-release.nix` has two sets:
  - `built`: what TulsiOS changes and must build itself (the Cinnamon 6.8 suite,
    `gtk3-o`, `otk`). CI builds it and pushes it to the TulsiOS cache.
  - `curated`: the opinionated app suite (Firefox, VLC, LibreOffice, GIMP, …) and the
    unchanged parts of the desktop. `ci/tulsi/check-upstream.sh` fails if anything in
    it depends on something in `built`, which would make users compile it.
- **Binary cache**: Attic at `https://cache.skarptech.org/tulsi` on the SkarpTech VPS.
  The `tulsi.cache` module adds it next to cache.nixos.org, trusting its public key
  (`tulsi.cache.publicKey`); without the key TulsiOS packages build locally, with a warning.
- **Ocimum Desktop** (`github.com/lukskrp/ocimum-desktop`, branch `ocimum`) is a hard
  fork of Cinnamon, currently based on 6.8.0. tulsipkgs builds `cinnamon` from it and
  the rest of the suite at the matching 6.8 releases. Ocimum changes do not have to stay
  small or rebase-friendly.
- **GTK 4, one temporary exception.** Cinnamon 6.8's background daemon (per-monitor
  wallpapers) is GTK 4 (≥ 4.18, gtk4-layer-shell). The rule for TulsiOS GUI code stays
  GTK3-O/OTK (ADR 0005). The daemon keeps GTK 4 until OTK has the GTK 4 features it
  needs; then it is ported to OTK and GTK 4 leaves the desktop.
- **OTK** (`github.com/lukskrp/OTK`), the ABI-breaking GTK 3 fork, installs side by
  side with GTK 3 (`libotk-3`, `otk-3.0.pc`, GIR `Otk`/`Odk`) and is built by tulsipkgs.
  Its next goal is porting the useful GTK 4 features.

## Consequences
- TulsiOS users download the Ocimum suite from the TulsiOS cache and everything else
  from cache.nixos.org; only packages in `built` cost CI time.
- Upgrades follow nixpkgs daily, but a sync that breaks the build or conflicts stops
  until someone fixes it.
- Bumping xapp rebuilds a few non-Cinnamon dependents (xfce4-settings, Mint apps);
  that is acceptable because none of them is in `curated`.
- New Cinnamon releases are no longer merged automatically; taking upstream changes is
  a deliberate porting decision.
- GTK 4 is in the desktop closure until the background daemon is ported to OTK.
