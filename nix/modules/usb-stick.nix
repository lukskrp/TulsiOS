# tulsi.usbStick: USB Stick Writer and Formatter, Tulsi's own (ADR 0040).
#
# Mint's USB Image Writer and Formatter in one window, plus `tulsi-stick` for
# terminals: write an ISO to a stick with verification, or wipe a stick and
# make one fresh partition (FAT32, exFAT, NTFS, ext4) for carrying files. Only
# removable USB drives are ever listed; writing and formatting name the drive
# to confirm. The app lives in its own repository (github:lukskrp/tulsistick),
# packaged here.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.tulsi.usbStick;
in
{
  options.tulsi.usbStick = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default =
        (config.ocimum.desktop.enable || config.sonic.desktop.enable || config.tulsi.dwm.enable)
        && !config.tulsi.installer.enable;
      defaultText = lib.literalMD "on with any TulsiOS desktop, except the live installer";
      description = "USB Stick Writer and Formatter: ISOs onto sticks, sticks ready for files.";
    };

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ../packages/tulsi-stick.nix { };
      defaultText = lib.literalExpression "pkgs.callPackage ../packages/tulsi-stick.nix { }";
      description = "The USB Stick Writer package.";
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ cfg.package ];
  };
}
