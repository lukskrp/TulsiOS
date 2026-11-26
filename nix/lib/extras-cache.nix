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
  # The same packages with unfree ones allowed, as tulsi.fonts.microsoft needs.
  unfree = import self.inputs.nixpkgs {
    inherit (pkgs.stdenv.hostPlatform) system;
    inherit (installed) overlays;
    config.allowUnfree = true;
  };
  # apps/tulsi-installer/tulsi_installer/render.py EXTRAS, as attributes.
  extras = [
    installed.libreoffice
    installed.bottles
    # Without its bundled Steam, which is unfree (tulsi-installer PACKAGE_EXTRAS).
    installed.lutris-free
    # Microsoft's fonts (ADR 0035): unfree, so nobody else's cache has them, and
    # their download site is slow and flaky.
    unfree.corefonts
  ];
in
pkgs.writeText "tulsios-extras-cache" (lib.concatMapStrings (p: "${p}\n") extras)
