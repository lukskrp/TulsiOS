# tulsi.backup: Backup for people, not just snapshots (ADR 0039).
#
# Snapshots undo mistakes on this disk; a backup is for a dead disk or a new
# machine. `tulsi-backup` mirrors home to a USB drive with a manifest (when,
# which TulsiOS, which software); restoring merges files back and prints the
# software list to reinstall (`tulsi install`, or the Software Center).
# Caches and trash are skipped; restores never delete.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.tulsi.backup;
in
{
  options.tulsi.backup = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default =
        (config.ocimum.desktop.enable || config.sonic.desktop.enable || config.tulsi.dwm.enable)
        && !config.tulsi.installer.enable;
      defaultText = lib.literalMD "on with any TulsiOS desktop, except the live installer";
      description = "Backup: your files and software list, to a USB drive and back.";
    };

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ../packages/tulsi-backup.nix { };
      defaultText = lib.literalExpression "pkgs.callPackage ../packages/tulsi-backup.nix { }";
      description = "The Backup package.";
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [
      cfg.package
      # The terminal way, and what scripts use; the window runs the same code.
      pkgs.rsync
    ];
  };
}
