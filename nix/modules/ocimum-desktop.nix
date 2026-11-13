# ocimum.desktop — the Ocimum Desktop.
#
# The desktop itself is the `cinnamon` package from tulsipkgs, which is built
# from the Ocimum Desktop fork (session name, logo, pinned apps). This module
# adds the TulsiOS defaults on top: theme, wallpaper and the Assistant shortcut.
# Users can change all of them in System Settings.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.ocimum.desktop;
  wallpaper = ../../data/ocimum-wallpaper.svg;
in
{
  options.ocimum.desktop = {
    enable = lib.mkEnableOption "the Ocimum Desktop";

    autoLoginUser = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "User to log in automatically, or null for the greeter.";
    };

    assistantShortcut = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      # Super+Space is Cinnamon's keyboard-layout switcher, so A for Assistant.
      default = "<Super>a";
      description = "Keyboard shortcut that opens the Assistant (null: none).";
    };
  };

  config = lib.mkIf cfg.enable {
    services.xserver.enable = true;
    services.xserver.desktopManager.cinnamon.enable = true;
    # Login screen: greetd + the Ocimum Greeter (ADR 0010). Never LightDM.
    ocimum.greeter = {
      enable = true;
      wallpaper = lib.mkDefault wallpaper;
    };
    services.displayManager.autoLogin = lib.mkIf (cfg.autoLoginUser != null) {
      enable = true;
      user = cfg.autoLoginUser;
    };

    # Green (basil) Mint-Y theme and the Ocimum wallpaper as defaults.
    services.xserver.desktopManager.cinnamon.extraGSettingsOverrides = ''
      [org.cinnamon.desktop.interface]
      gtk-theme='Mint-Y-Dark'
      icon-theme='Mint-Y'

      [org.cinnamon.theme]
      name='Mint-Y-Dark'

      [org.cinnamon.desktop.wm.preferences]
      theme='Mint-Y'

      [org.cinnamon.desktop.background]
      picture-uri='file://${wallpaper}'
      picture-options='zoom'
    '';

    # Custom keybindings live under a relocatable schema, which gschema
    # overrides cannot reach, so they are system dconf defaults instead.
    programs.dconf = lib.mkIf (cfg.assistantShortcut != null) {
      enable = true;
      profiles.user.databases = [
        {
          settings = {
            "org/cinnamon/desktop/keybindings".custom-list = [ "custom0" ];
            "org/cinnamon/desktop/keybindings/custom-keybindings/custom0" = {
              name = "Assistant";
              command = "ocimum-assistant";
              binding = [ cfg.assistantShortcut ];
            };
          };
        }
      ];
    };
  };
}
