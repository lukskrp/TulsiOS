# tulsi.dwm — dwm as TulsiOS's tiling session (ADR 0016).
#
# Suckless dwm 6.8 with one patch, the system tray (data/dwm/dwm-systray-6.8.diff,
# ported to the 6.8 release), and TulsiOS's config.h: Super as the modifier,
# Super+A for the Assistant, Super+S for the Software Center. It runs on XLibre
# like Ocimum, and logs in through the Ocimum Greeter.
#
# A bare window manager lacks what Cinnamon brings along, and TulsiOS needs it:
# XDG autostart and graphical-session.target (Starah's first-login window, the
# extension watcher), a polkit agent (password prompts of the Software Center),
# a notification daemon (Starah requests, adopt notices) and GTK theme settings.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.tulsi.dwm;

  background =
    if cfg.wallpaper != null then
      "${pkgs.xwallpaper}/bin/xwallpaper --zoom ${cfg.wallpaper}"
    else
      "${pkgs.xsetroot}/bin/xsetroot -solid ${lib.escapeShellArg cfg.background}";
in
{
  options.tulsi.dwm = {
    enable = lib.mkEnableOption "dwm (with a system tray) as the TulsiOS tiling session";

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.dwm.override {
        conf = ../../data/dwm/config.h;
        patches = [
          ../../data/dwm/dwm-systray-6.8.diff
          # Colours from X resources, reloaded on xrdb -merge (themes, ADR 0021).
          ../../data/dwm/dwm-colours-xrdb-6.8.diff
        ];
      };
      defaultText = lib.literalExpression "pkgs.dwm with TulsiOS's config.h, the systray and colour patches";
      description = "The dwm package.";
    };

    wallpaper = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = null;
      description = "Wallpaper of the session (and of the greeter), or null for a plain background.";
    };

    background = lib.mkOption {
      type = lib.types.str;
      default = "#1b1f1c";
      description = "Background colour when there is no wallpaper.";
    };
  };

  config = lib.mkIf cfg.enable {
    services.xserver.enable = true;
    services.xserver.windowManager.dwm = {
      enable = true;
      package = cfg.package;
      extraSessionCommands = ''
        # The person's theme (tulsi-theme), before dwm reads its colours.
        if [ -f "$HOME/.config/tulsi/theme.Xresources" ]; then
          ${pkgs.xrdb}/bin/xrdb -merge "$HOME/.config/tulsi/theme.Xresources" || true
        fi
        if [ -f "$HOME/.config/tulsi/theme.wallpaper" ]; then
          ${pkgs.xwallpaper}/bin/xwallpaper --zoom "$(cat "$HOME/.config/tulsi/theme.wallpaper")" || ${background} || true
        else
          ${background} || true
        fi
        # The status text in the bar (date and time).
        ${pkgs.slstatus}/bin/slstatus &
      '';
    };

    # Starts graphical-session.target and the XDG autostart entries, which only
    # desktop environments do on their own.
    services.xserver.desktopManager.runXdgAutostartIfNone = true;

    ocimum.greeter.wallpaper = lib.mkDefault cfg.wallpaper;

    environment.systemPackages = [
      pkgs.dmenu
      # st with its colours from X resources (a theme's terminal colours).
      (pkgs.st.override { patches = [ ../../data/dwm/st-colours-xrdb-0.9.3.diff ]; })
      pkgs.slstatus
      pkgs.mint-themes
      pkgs.mint-y-icons
      pkgs.adwaita-icon-theme
    ];

    programs.slock.enable = true;
    programs.dconf.enable = true;

    # The tray icon (XEmbed): the systray patch does not show indicators.
    programs.nm-applet = lib.mkIf config.networking.networkmanager.enable {
      enable = true;
      indicator = false;
    };

    # Password prompts for the Software Center, tulsi-adopt and others.
    systemd.user.services.tulsi-polkit-agent = {
      description = "polkit authentication agent for the dwm session";
      wantedBy = [ "graphical-session.target" ];
      partOf = [ "graphical-session.target" ];
      after = [ "graphical-session.target" ];
      serviceConfig = {
        ExecStart = "${pkgs.polkit_gnome}/libexec/polkit-gnome-authentication-agent-1";
        Restart = "on-failure";
      };
    };

    # Notifications: dunst starts on the first one (D-Bus activation).
    services.dbus.packages = [ pkgs.dunst ];
    systemd.packages = [ pkgs.dunst ];

    # GTK apps get the TulsiOS look without a settings daemon.
    environment.etc."xdg/gtk-3.0/settings.ini".text = ''
      [Settings]
      gtk-theme-name=Mint-Y-Dark
      gtk-icon-theme-name=Mint-Y
      gtk-cursor-theme-name=Adwaita
      gtk-application-prefer-dark-theme=1
    '';
  };
}
