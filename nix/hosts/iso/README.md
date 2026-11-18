# Installer ISO (Phase 7)

Will hold the live ISO (`nixosConfigurations.tulsi-iso`, see ADR 0016). The pieces it
puts together already exist:

- `tulsi.installer.enable` / `tulsi.installer.calamares.enable` (nix/modules/installer.nix):
  `tulsi-install-system` and Calamares with TulsiOS's settings, branding and `tulsios` job;
- `tulsi.installer.offlineSystems` plus `nix/lib/install-closure.nix` and
  `nix/lib/offline-rebuild-inputs.nix`: an Ocimum and a dwm reference install, and what
  rebuilding their per-machine parts needs, so installing needs no network (as in
  nix/tests/install.nix). Real hardware adds other kernel modules; check that the
  initrd still rebuilds offline on the ISO;
- the ISO itself: nixpkgs' `installation-cd-graphical-calamares.nix`, an Ocimum live
  session with autologin, tulsid/Starah/Software Center off, TulsiOS names and artwork.
