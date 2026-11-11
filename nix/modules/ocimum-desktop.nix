# ocimum.desktop — the Ocimum Desktop (Cinnamon-based).
#
# Phase 1: wraps stock nixpkgs Cinnamon so hosts already depend on this
# option. Phase 6 swaps in the forked Cinnamon (desktop/cinnamon) via an
# overlay and adds TulsiOS branding, theme, layout and applets.
{ config, lib, ... }:

let
  cfg = config.ocimum.desktop;
in
{
  options.ocimum.desktop = {
    enable = lib.mkEnableOption "the Ocimum Desktop";
    autoLoginUser = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "User to log in automatically, or null for the greeter.";
    };
  };

  config = lib.mkIf cfg.enable {
    services.xserver.enable = true;
    services.xserver.desktopManager.cinnamon.enable = true;
    services.xserver.displayManager.lightdm.enable = true;
    services.displayManager.autoLogin = lib.mkIf (cfg.autoLoginUser != null) {
      enable = true;
      user = cfg.autoLoginUser;
    };
  };
}
