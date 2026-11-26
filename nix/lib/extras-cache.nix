# What the TulsiOS cache must hold for the installer's "Extra software" page
# (ADR 0032, 0034): each extra as an installed system builds it, so that ticking it
# downloads instead of compiling. Each release builds this and pushes its closure
# (docs/RELEASING.md), as for SonicDE.
#
# Its text names every path, so its closure is all of them.
{ self, pkgs }:
let
  inherit (pkgs) lib;
  # An installed system's own package set (its overlays and settings).
  installed = (import ./reference-system.nix { inherit self; boot = "uefi"; desktop = "ocimum"; }).pkgs;
  # apps/tulsi-installer/tulsi_installer/render.py EXTRAS, as attributes.
  extras = [
    installed.libreoffice
    installed.bottles
    # Without its bundled Steam, which is unfree (tulsi-installer PACKAGE_EXTRAS).
    installed.lutris-free
  ];
in
pkgs.writeText "tulsios-extras-cache" (lib.concatMapStrings (p: "${p}\n") extras)
