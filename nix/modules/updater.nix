# tulsi.updater: Update Manager and Timeshift, Tulsi-style (ADR 0038).
#
# Mint's Update Manager plus Timeshift: a release check every day (with a
# desktop notification when one is out), one window for the release, the older
# system versions, and the /home snapshots. Upgrades run through tulsid, so
# each is recorded and can be undone; a snapshot of /home is taken first when
# snapshots are on. Nothing here reinstalls from scratch: the boot menu's
# older versions and File History do the going back.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.tulsi.updater;

  # `tulsi upgrade`, snapshotting /home first when snapper manages it (the
  # Update Manager runs this; terminals keep plain `tulsi upgrade`).
  upgradeWrapper = pkgs.writeShellApplication {
    name = "tulsi-upgrade";
    runtimeInputs = [
      pkgs.snapper
      config.tulsi.daemon.package
    ];
    text = ''
      # A home snapshot first (when snapshots are on and snapper manages
      # /home), then the release upgrade the Update Manager also runs.
      ${lib.optionalString cfg.snapshotBeforeUpgrade ''
        if snapper -c home list >/dev/null 2>&1; then
          snapper -c home create --description "before upgrade $(date -u +%FT%TZ)" \
            --cleanup-algorithm number || echo "tulsi-upgrade: snapshot failed, continuing anyway" >&2
        fi
      ''}
      exec tulsi upgrade "$@"
    '';
  };
in
{
  options.tulsi.updater = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default =
        (config.ocimum.desktop.enable || config.sonic.desktop.enable || config.tulsi.dwm.enable)
        && !config.tulsi.installer.enable;
      defaultText = lib.literalMD "on with any TulsiOS desktop, except the live installer";
      description = "Update Manager: daily release checks, the release window, and a snapshot before upgrading.";
    };

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ../packages/tulsi-update-manager.nix { };
      defaultText = lib.literalExpression "pkgs.callPackage ../packages/tulsi-update-manager.nix { }";
      description = "The Update Manager package.";
    };

    checkInterval = lib.mkOption {
      type = lib.types.str;
      default = "daily";
      example = "hourly";
      description = ''
        How often to check for a new TulsiOS release (systemd OnCalendar).
        A desktop notification appears once per release (`tulsi upgrade
        --check --notify` remembers what it announced).
      '';
    };

    snapshotBeforeUpgrade = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = ''
        Take a /home snapshot before a release upgrade (`tulsi-upgrade`, which
        the Update Manager runs). Needs snapper managing /home (File History);
        without it the upgrade runs as it does today.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [
      cfg.package
    ]
    ++ lib.optional cfg.snapshotBeforeUpgrade upgradeWrapper;

    # The release check, once per user session's day: tulsid answers from the
    # release branch, and only an available release notifies.
    systemd.user.services.tulsi-upgrade-check = {
      description = "Check for a new TulsiOS release";
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${config.tulsi.daemon.package}/bin/tulsi upgrade --check --notify";
      };
    };
    systemd.user.timers.tulsi-upgrade-check = {
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnCalendar = cfg.checkInterval;
        Persistent = true;
      };
    };
  };
}
