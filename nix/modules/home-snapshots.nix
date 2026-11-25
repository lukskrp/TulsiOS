# tulsi.homeSnapshots: a history of everyone's files in /home (ADR 0027).
#
# Off until the person turns it on (the Welcome window after installing, or
# `tulsi config`). Needs /home on btrfs, the installer's default: a snapshot is
# then instant and only takes the space of what changed since.
#
# snapper keeps the newest `hourly` hourly, `daily` daily and `weekly` weekly
# snapshots of /home in /home/.snapshots. Each snapshot keeps every home's own
# permissions, so people browse only their own files (File History,
# `tulsi-file-history`). Members of `wheel` may delete snapshots ("Free space now").
# Snapshots are on the same disk as the files: they undo deletes and edits,
# they are not a backup.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.tulsi.homeSnapshots;
  homeFs = config.fileSystems."/home" or config.fileSystems."/" or { fsType = ""; };
in
{
  options.tulsi.welcome = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default =
        (config.ocimum.desktop.enable || config.sonic.desktop.enable || config.tulsi.dwm.enable)
        && !config.tulsi.installer.enable;
      defaultText = lib.literalMD "on with any TulsiOS desktop, except the live installer";
      description = ''
        The Welcome window at each person's first login after installing (not in
        virtual machines), which offers File History, and File History itself.
      '';
    };
    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ../packages/ocimum-file-history.nix { };
      defaultText = lib.literalExpression "pkgs.callPackage ../packages/ocimum-file-history.nix { }";
      description = "File History and the Welcome window.";
    };
  };

  options.tulsi.homeSnapshots = {
    enable = lib.mkEnableOption "hourly, daily and weekly snapshots of /home (needs btrfs)";
    hourly = lib.mkOption {
      type = lib.types.ints.unsigned;
      default = 24;
      description = "Hourly snapshots kept.";
    };
    daily = lib.mkOption {
      type = lib.types.ints.unsigned;
      default = 7;
      description = "Daily snapshots kept.";
    };
    weekly = lib.mkOption {
      type = lib.types.ints.unsigned;
      default = 4;
      description = "Weekly snapshots kept.";
    };
  };

  config = lib.mkMerge [
    (lib.mkIf config.tulsi.welcome.enable {
      environment.systemPackages = [
        config.tulsi.welcome.package
        # The TulsiOS Wiki (help pages, offline), which the Welcome window opens.
        (pkgs.callPackage ../packages/tulsi-wiki.nix { })
      ];
      # Nemo's "Previous Versions…" action and Dolphin's service menu.
      environment.pathsToLink = [
        "/share/nemo"
        "/share/kio"
        "/share/tulsios"
      ];
    })
    (lib.mkIf cfg.enable {
      assertions = [
        {
          assertion = homeFs.fsType == "btrfs";
          message = "tulsi.homeSnapshots needs /home on btrfs (it is ${homeFs.fsType}).";
        }
      ];

      services.snapper = {
        snapshotInterval = "hourly";
        cleanupInterval = "1h";
        configs.home = {
          SUBVOLUME = "/home";
          ALLOW_GROUPS = [ "wheel" ];
          TIMELINE_CREATE = true;
          TIMELINE_CLEANUP = true;
          TIMELINE_LIMIT_HOURLY = cfg.hourly;
          TIMELINE_LIMIT_DAILY = cfg.daily;
          TIMELINE_LIMIT_WEEKLY = cfg.weekly;
          TIMELINE_LIMIT_MONTHLY = 0;
          TIMELINE_LIMIT_YEARLY = 0;
        };
      };

      # snapper needs /home/.snapshots to be a subvolume of its own; everyone may
      # look inside (each snapshot keeps the homes' own permissions).
      systemd.services.tulsi-home-snapshots-setup = {
        description = "Prepare /home for snapshots";
        wantedBy = [ "multi-user.target" ];
        before = [
          "snapper-timeline.service"
          "snapper-cleanup.service"
          "snapperd.service"
        ];
        after = [ "local-fs.target" ];
        path = [ pkgs.btrfs-progs ];
        serviceConfig.Type = "oneshot";
        serviceConfig.RemainAfterExit = true;
        script = ''
          if ! btrfs subvolume show /home/.snapshots >/dev/null 2>&1; then
            if [ -e /home/.snapshots ]; then
              echo "/home/.snapshots exists and is not a subvolume; leaving it alone" >&2
              exit 1
            fi
            btrfs subvolume create /home/.snapshots
          fi
          chmod 0755 /home/.snapshots
        '';
      };

      environment.systemPackages = [ pkgs.snapper ];
    })
  ];
}
