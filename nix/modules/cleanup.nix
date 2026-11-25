# tulsi.cleanup: keep the disk from filling with old system versions (ADR 0025).
#
# Every change, undo and upgrade adds a NixOS generation, and nothing removed
# them. Undo doesn't need them (tulsid rebuilds from the git record in
# /etc/nixos), only the boot menu's "older versions" does. So weekly:
#   - generations older than keepDays go, but the newest keepGenerations, the
#     current one and the booted one always stay;
#   - store paths nothing uses any more are deleted (nix-store --gc).
# Identical files in the store are shared as they are added, the boot menu
# lists at most keepGenerations versions, and the system journal is capped.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.tulsi.cleanup;

  cleanup = pkgs.writeShellApplication {
    name = "tulsi-cleanup";
    runtimeInputs = with pkgs; [
      coreutils
      gnused
      procps
      config.nix.package
    ];
    text = ''
      profile=/nix/var/nix/profiles/system
      keep_days=${toString cfg.keepDays}
      keep_generations=${toString cfg.keepGenerations}

      # Not while a change is being built and switched to.
      for _ in $(seq 360); do
        pgrep -f 'nixos-rebuild|switch-to-configuration' >/dev/null || break
        sleep 10
      done

      gen_of() { readlink "$1" | sed -nE 's/^system-([0-9]+)-link$/\1/p'; }
      current=$(gen_of "$profile")
      booted=$(readlink -f /run/booted-system || true)
      cutoff=$(( $(date +%s) - keep_days * 86400 ))

      mapfile -t all < <(find /nix/var/nix/profiles -maxdepth 1 -name 'system-*-link' -printf '%f\n' \
        | sed -nE 's/^system-([0-9]+)-link$/\1/p' | sort -n)
      mapfile -t newest < <(printf '%s\n' "''${all[@]}" | tail -n "$keep_generations")

      old=()
      for g in "''${all[@]}"; do
        link="$profile-$g-link"
        [ "$g" = "$current" ] && continue
        printf '%s\n' "''${newest[@]}" | grep -qx "$g" && continue
        [ -n "$booted" ] && [ "$(readlink -f "$link")" = "$booted" ] && continue
        # The link is made when the generation is: its own time is the generation's.
        [ "$(stat -c %Y "$link")" -lt "$cutoff" ] || continue
        old+=("$g")
      done

      if [ ''${#old[@]} -gt 0 ]; then
        echo "removing system generations: ''${old[*]}"
        nix-env -p "$profile" --delete-generations "''${old[@]}"
      else
        echo "no system generation is old enough to remove"
      fi
      nix-store --gc
    '';
  };
in
{
  options.tulsi.cleanup = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = config.tulsi.daemon.enable;
      defaultText = lib.literalExpression "config.tulsi.daemon.enable";
      description = "Weekly removal of old system generations and unused store paths.";
    };
    keepDays = lib.mkOption {
      type = lib.types.ints.positive;
      default = 30;
      description = "Generations younger than this many days are kept.";
    };
    trashDays = lib.mkOption {
      type = lib.types.ints.positive;
      default = 30;
      description = "Files that have been in a person's trash longer than this are deleted.";
    };
    keepGenerations = lib.mkOption {
      type = lib.types.ints.positive;
      default = 10;
      description = ''
        The newest generations always kept, however old, and how many the boot
        menu lists.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [
      cleanup
      pkgs.trash-cli
    ];

    systemd.services.tulsi-cleanup = {
      description = "Remove old TulsiOS system versions and unused files";
      serviceConfig = {
        Type = "oneshot";
        ExecStart = lib.getExe cleanup;
        Nice = 19;
        IOSchedulingClass = "idle";
      };
    };
    systemd.timers.tulsi-cleanup = {
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnCalendar = "weekly";
        Persistent = true;
        RandomizedDelaySec = "1h";
      };
    };

    # The trash empties itself of what has been there over trashDays, on every
    # desktop; `trash` (trash-cli) also works in terminals and dwm.
    systemd.user.services.tulsi-trash-expire = {
      description = "Empty what has been in the trash for over ${toString cfg.trashDays} days";
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${pkgs.trash-cli}/bin/trash-empty -f ${toString cfg.trashDays}";
      };
    };
    systemd.user.timers.tulsi-trash-expire = {
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnCalendar = "daily";
        Persistent = true;
      };
    };

    nix.settings.auto-optimise-store = lib.mkDefault true;
    boot.loader.systemd-boot.configurationLimit = lib.mkDefault cfg.keepGenerations;
    boot.loader.grub.configurationLimit = lib.mkDefault cfg.keepGenerations;
    services.journald.settings.Journal.SystemMaxUse = lib.mkDefault "1G";
  };
}
