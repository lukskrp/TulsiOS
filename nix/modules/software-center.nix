# ocimum.softwareCenter — GUI to install and remove software through tulsid.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.ocimum.softwareCenter;
in
{
  options.ocimum.softwareCenter = {
    enable = lib.mkEnableOption "the Ocimum Software Center";

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ../packages/ocimum-software-center.nix { };
      defaultText = lib.literalExpression "pkgs.callPackage ../packages/ocimum-software-center.nix { }";
      description = "The Ocimum Software Center package.";
    };

    upgradeCheck.enable = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = ''
        Look for a newer TulsiOS release once a day and announce it as a desktop
        notification with an Upgrade button (ADR 0017). Nothing is upgraded without
        the user.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = config.tulsi.daemon.enable;
        message = "ocimum.softwareCenter requires tulsi.daemon.enable = true.";
      }
    ];
    environment.systemPackages = [ cfg.package ];

    # `tulsi upgrade --check --notify` announces each new release once; its button
    # opens the Software Center's Updates page.
    systemd.user.services.tulsi-upgrade-check = lib.mkIf cfg.upgradeCheck.enable {
      description = "Look for a newer TulsiOS release";
      after = [ "graphical-session.target" ];
      path = [ cfg.package ];
      serviceConfig = {
        # Waits up to an hour for the notification's button.
        Type = "simple";
        ExecStart = "${config.tulsi.daemon.package}/bin/tulsi upgrade --check --notify";
      };
    };
    systemd.user.timers.tulsi-upgrade-check = lib.mkIf cfg.upgradeCheck.enable {
      description = "Look for a newer TulsiOS release daily";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnStartupSec = "15min";
        OnUnitActiveSec = "1d";
        RandomizedDelaySec = "1h";
        Persistent = true;
      };
    };
  };
}
