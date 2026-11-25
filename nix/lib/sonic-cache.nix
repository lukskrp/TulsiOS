# What the TulsiOS cache must hold for SonicDE (ADR 0020), which installs online only:
# the SonicDE reference installs (both boot loaders), what nixos-install needs to
# rebuild their per-machine parts, and popular KDE apps as Sonic builds, so that
# installing SonicDE, or one of these apps on it, downloads instead of compiling.
# Each release builds this and pushes its closure (docs/RELEASING.md).
#
# Its text names every path, so its closure is all of them.
{ self, pkgs }:
let
  inherit (pkgs) lib;
  references = map (boot: import ./reference-system.nix { inherit self boot; desktop = "sonic"; }) [
    "uefi"
    "bios"
  ];
  # On a SonicDE machine, kdePackages is Sonic's set (nix/modules/sonic-desktop.nix).
  sonicKde = (lib.head references).pkgs.kdePackages;
  popularApps = with sonicKde; [
    kate
    okular
    gwenview
    ark
    kcalc
    elisa
    kdenlive
    filelight
    partitionmanager
    kcharselect
    kolourpaint
    kdeconnect-kde
    skanpage
  ];
  paths =
    map (r: r.config.system.build.toplevel) references
    ++ lib.concatMap (import ./offline-rebuild-inputs.nix) references
    ++ popularApps;
in
pkgs.writeText "tulsios-sonic-cache" (lib.concatMapStrings (p: "${p}\n") paths)
