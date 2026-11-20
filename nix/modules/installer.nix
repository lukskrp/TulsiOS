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
        inherit (cfg) upstream sourceInfo;
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

    upstream = lib.mkOption {
      type = lib.types.str;
      default = "github:lukskrp/TulsiOS/stable";
      description = ''
        Where installed machines get TulsiOS releases from: the `tulsi` input of
        their system flake, which `tulsi upgrade` follows (ADR 0017).
      '';
    };

    sourceInfo = lib.mkOption {
      type = lib.types.nullOr (
        lib.types.submodule {
          options = {
            rev = lib.mkOption { type = lib.types.str; };
            narHash = lib.mkOption { type = lib.types.str; };
            lastModified = lib.mkOption { type = lib.types.int; };
          };
        }
      );
      default = null;
      description = ''
        Git revision, narHash and lastModified of tulsi.daemon.bootstrap.source (the
        TulsiOS flake sets them from `self`). With them, the installed flake.lock pins
        `upstream` to exactly that source, found in the store without a network.
        Without them, installed machines use the source as a local path and cannot
        upgrade.
      '';
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
