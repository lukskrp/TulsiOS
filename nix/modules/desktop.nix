# tulsi.desktop — which desktop a TulsiOS machine runs (ADR 0016).
#
# The installer asks for one of two and installs only that one:
#   "ocimum"  Ocimum Desktop (the Cinnamon fork, ocimum.desktop)
#   "dwm"     dwm with a system tray (tulsi.dwm), for people who like tiling
# Both log in through the Ocimum Greeter on XLibre and get Starah and the
# TulsiOS way of installing software. Switching later is one line in
# configuration.nix: tulsi.desktop.session = "dwm";
{
  config,
  lib,
  ...
}:

let
  cfg = config.tulsi.desktop;
in
{
  options.tulsi.desktop = {
    session = lib.mkOption {
      type = lib.types.nullOr (
        lib.types.enum [
          "ocimum"
          "dwm"
        ]
      );
      default = null;
      example = "dwm";
      description = "The desktop of this machine: Ocimum Desktop or dwm (null: set up neither here).";
    };

    autoLoginUser = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "User to log in automatically, or null for the greeter.";
    };
  };

  config = lib.mkMerge [
    (lib.mkIf (cfg.session == "ocimum") {
      ocimum.desktop = {
        enable = true;
        autoLoginUser = lib.mkDefault cfg.autoLoginUser;
      };
    })

    # What ocimum.desktop turns on besides Cinnamon, for dwm.
    (lib.mkIf (cfg.session == "dwm") {
      tulsi.dwm.enable = true;
      ocimum.greeter.enable = true;
      services.displayManager.defaultSession = "none+dwm";
      services.starah.enable = lib.mkDefault true;
      tulsi.adopt.enable = lib.mkDefault config.ocimum.softwareCenter.enable;
      services.displayManager.autoLogin = lib.mkIf (cfg.autoLoginUser != null) {
        enable = true;
        user = cfg.autoLoginUser;
      };
    })
  ];
}
