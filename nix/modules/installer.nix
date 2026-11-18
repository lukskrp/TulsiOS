# tulsi.installer — what installs TulsiOS (ADR 0016).
#
#   tulsi-install-system  writes the system flake into <root>/etc/nixos and runs
#                         nixos-install; the live ISO and the VM tests use it
#   calamares.enable      the graphical installer (Qt, live ISO only), whose
#                         `tulsios` job calls tulsi-install-system
#   offlineSystems        reference installs whose closures are kept in the store,
#                         so nixos-install needs no network: only the parts that
#                         differ per machine (disks, hostname, users) are built
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.tulsi.installer;

  calamares = pkgs.calamares-nixos.override {
    calamares-nixos-extensions = pkgs.callPackage ../packages/calamares-tulsios-extensions.nix { };
  };
  autostart = pkgs.makeAutostartItem {
    name = "calamares";
    package = calamares;
  };
in
{
  options.tulsi.installer = {
    enable = lib.mkEnableOption "tulsi-install-system, which installs TulsiOS onto a mounted disk";

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ../packages/tulsi-installer.nix {
        source = config.tulsi.daemon.bootstrap.source;
        nixos-install-tools = pkgs.symlinkJoin {
          name = "nixos-install-tools";
          paths = [
            config.system.build.nixos-install
            config.system.build.nixos-generate-config
          ];
        };
      };
      defaultText = lib.literalExpression "tulsi-installer for tulsi.daemon.bootstrap.source";
      description = "The tulsi-installer package.";
    };

    calamares.enable = lib.mkEnableOption "the Calamares installer with TulsiOS's settings, started at login";

    offlineSystems = lib.mkOption {
      type = lib.types.listOf lib.types.package;
      default = [ ];
      description = ''
        Toplevels of reference TulsiOS installs (e.g. one per desktop). Their closures
        are kept in this system's store, so installing needs no network.
      '';
    };

    buildDependencies = lib.mkOption {
      type = lib.types.listOf lib.types.package;
      default = [ ];
      description = ''
        What building the per-machine parts of a TulsiOS system needs, offline:
        nix/lib/install-closure.nix (build tools) plus
        nix/lib/offline-rebuild-inputs.nix applied to each reference system.
      '';
    };
  };

  config = lib.mkIf cfg.enable (
    lib.mkMerge [
      {
        assertions = [
          {
            assertion = config.tulsi.daemon.bootstrap.source != null;
            message = "tulsi.installer needs tulsi.daemon.bootstrap.source (the TulsiOS flake's nixosModules.default sets it).";
          }
        ];
        environment.systemPackages = [ cfg.package ];
        nix.settings.experimental-features = [
          "nix-command"
          "flakes"
        ];
        system.extraDependencies = cfg.offlineSystems ++ cfg.buildDependencies;
      }
      (lib.mkIf cfg.calamares.enable {
        environment.systemPackages = [
          calamares
          autostart
          pkgs.glibcLocales
        ];
        # Calamares runs as the live user and installs through pkexec.
        security.polkit.enablePkexecWrapper = true;
        # KPMcore (Calamares' partitioning) needs its helper.
        programs.partition-manager.enable = true;
        i18n.supportedLocales = [ "all" ];
      })
    ]
  );
}
