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
  # Both ship with the Ocimum fork (the `cinnamon` package).
  wallpaper = "${pkgs.cinnamon}/share/backgrounds/ocimum/tulsios-leaf.png";
  startIcons = {
    coloured = "tulsi-start";
    white = "tulsi-start-white";
  };
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

    startIcon = lib.mkOption {
      type = lib.types.enum (lib.attrNames startIcons);
      default = "coloured";
      description = ''
        Default icon of the panel's menu (start) button: the full-colour TulsiOS
        logo, which suits light and dark panels, or a white one for dark panels.
        Users can pick either in the menu applet's settings (`tulsi-start`,
        `tulsi-start-white`).
      '';
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
    # Starah (ADR 0011): agents get privileges only through the levels the human
    # chooses at first login.
    services.starah.enable = lib.mkDefault true;
    # apt/dnf/pacman, downloaded packages and foreign binaries lead to the
    # Software Center or the Assistant (ADR 0013).
    tulsi.adopt.enable = lib.mkDefault config.ocimum.softwareCenter.enable;
    services.displayManager.autoLogin = lib.mkIf (cfg.autoLoginUser != null) {
      enable = true;
      user = cfg.autoLoginUser;
    };

    # System Settings → Backgrounds lists the Ocimum wallpapers from here.
    environment.pathsToLink = [
      "/share/backgrounds"
      "/share/cinnamon-background-properties"
    ];

    # Mint-Y-Dark, the Tulsi Leaf wallpaper and the TulsiOS start button as defaults.
    services.xserver.desktopManager.cinnamon.extraGSettingsOverrides = ''
      [org.cinnamon]
      app-menu-icon-name='${startIcons.${cfg.startIcon}}'

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
