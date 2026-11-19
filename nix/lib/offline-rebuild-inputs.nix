# What nixos-install needs, besides a reference system's own closure, to rebuild
# the parts of that system that differ per machine (hostname, users, time zone,
# keyboard, file systems) without a network.
#
# Those answers change small leaf files (etc/hostname, fstab, users-groups.json,
# the X keyboard config, …), and then everything above them is rebuilt too: /etc
# and its systemd unit trees, the system profile (buildEnv), the initrd and the
# toplevel. Rebuilding needs the outputs of every input of those derivations, and
# some are not in the runtime closure: the initrd is compressed (keeps no
# references), buildEnv drops shadowed packages, and build tools (xkbvalidate,
# xsltproc, …) are used at build time only.
#
# For each such derivation we keep a file listing its attributes. Its text
# names every input's store path, so those paths are kept with it.
# (`inputDerivation` would miss inputs passed through files or structured attrs.)
#
# system: a nixosSystem (e.g. one of tulsi.installer's reference installs).
system:
let
  c = system.config;
  inherit (system) pkgs;
  inherit (pkgs) lib;

  inputsOf =
    d: pkgs.writeText "inputs-of-${d.name}" (builtins.toJSON (removeAttrs d.drvAttrs [ "passthru" ]));

  derivations = lib.filter lib.isDerivation;
  sources = attrs: derivations (map (e: e.source or null) (lib.attrValues attrs));
  unitFiles = units: derivations (map (u: u.unit or null) (lib.attrValues units));
in
map inputsOf (
  [
    c.system.build.toplevel
    c.system.build.etc
    c.system.path
    c.system.build.initialRamdisk
  ]
  # The boot loader's install script names the disk (GRUB's device).
  ++ derivations [ c.system.build.installBootLoader ]
  ++ sources c.environment.etc
  ++ sources c.boot.initrd.systemd.contents
  ++ unitFiles c.systemd.units
  ++ unitFiles c.systemd.user.units
  ++ unitFiles c.boot.initrd.systemd.units
)
++ [ pkgs.buildPackages.xkbvalidate ]
