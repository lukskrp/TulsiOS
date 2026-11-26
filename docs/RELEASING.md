# Releasing TulsiOS

Installed machines follow the `stable` branch (ADR 0017): whatever is on `stable` is
offered to every installed machine as an upgrade. So `stable` only moves here.

## A release

1. **On `main`:** bump `VERSION` (e.g. `0.1.0` → `0.2.0`; a patch release such as
   `0.1.1` for fixes only). If tulsipkgs has fixes, `nix flake update nixpkgs` first.
   Push, and wait for CI (`nix flake check`) to pass.
2. **Move `stable`:** fast-forward it to that commit and push.

       git push git@github.com:lukskrp/TulsiOS.git main:stable

   CI runs on `stable` too. From now on installed machines are offered the release
   (their daily check, or `tulsi upgrade --check`).
3. **Tag it:** `git tag -a v0.2.0 -m "TulsiOS 0.2.0"` on that commit, and push the tag.
4. **Build the ISO from a clean checkout of that commit**, so the ISO's installed
   `flake.lock` names a revision that exists on `stable`:

       git clone --branch v0.2.0 https://github.com/lukskrp/TulsiOS && cd TulsiOS
       nix build .#iso
       sha256sum result/iso/*.iso > tulsios-0.2.0-x86_64-linux.iso.sha256

   A tree with uncommitted changes builds an ISO whose installs carry an all-zero
   revision: they install fine, but use it only for testing.
5. **Fill the cache for SonicDE** (ADR 0020), from the same checkout. SonicDE is not on
   the ISO: installs of it download everything from the TulsiOS cache, so its closure
   must be there before the ISO is published, or those installs compile Plasma for
   hours. `sonic-cache` is the SonicDE reference installs (UEFI and BIOS), what
   rebuilding their per-machine parts needs, and popular KDE apps as Sonic builds
   (Kate, Okular, Gwenview, Ark, …; the list is in `nix/lib/sonic-cache.nix`).

       nix build .#sonic-cache
       attic push tulsi ./result

   The first build of a new Sonic release takes hours; later ones reuse the cache.

   Then the installer's extra software (ADR 0032; LibreOffice), which installs
   download when it is ticked:

       nix build .#extras-cache
       attic push tulsi ./result
6. **GitHub Release** for the tag: the ISO, its `.sha256`, and release notes (what
   changed, known limits). The ISO is about 4 GB, built locally, not in CI.

## Checks before moving `stable`

- CI is green on the commit (`nix flake check`, including the install and ISO tests).
- An installed machine from the previous ISO upgrades (`tulsi upgrade`), boots, and
  `tulsi undo` takes the upgrade back.

## Fixing a bad release

Move `stable` forward with a fix (a new patch release). Do not move it backwards:
machines that already upgraded would not be offered the older commit. Users can always
`tulsi undo` the upgrade on their machine.
