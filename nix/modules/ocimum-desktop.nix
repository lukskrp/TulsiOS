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
  # Panel applets in order, as gsettings' "panel:side:position:uuid" entries.
  applets = side: lib.imap0 (i: uuid: "panel1:${side}:${toString i}:${uuid}@cinnamon.org");
  enabledApplets =
    "["
    + lib.concatMapStringsSep ", " (a: "'${a}'") (
      applets "left" [
        "menu"
        "show-desktop"
        "panel-launchers"
        "separator"
        "grouped-window-list"
      ]
      ++ applets "right" [
        "systray"
        "xapp-status"
        "notifications"
        "printers"
        "removable-drives"
        "trash"
        "keyboard"
        "favorites"
        "network"
        "sound"
        "power"
        "calendar"
        "cornerbar"
      ]
    )
    + "]";

  # Runs once per user, at the session's Initialization phase (before
  # nemo-desktop draws the desktop): copies the launchers onto the desktop and
  # gives them positions in the top-right corner. Nemo trusts an executable
  # launcher, and reads an icon's position from the file's
  # metadata::nemo-icon-position ("x,y" in desktop pixels; it snaps to its grid).
  desktopDefaults = pkgs.writeShellApplication {
    name = "ocimum-desktop-defaults";
    runtimeInputs = with pkgs; [
      coreutils
      gawk
      gnugrep
      glib
      xdg-user-dirs
      xrandr
    ];
    text = ''
      stamp="''${XDG_STATE_HOME:-$HOME/.local/state}/ocimum/desktop-defaults"
      [ -e "$stamp" ] && exit 0

      desk=$(xdg-user-dir DESKTOP 2>/dev/null || true)
      if [ -z "$desk" ] || [ "$desk" = "$HOME" ]; then desk="$HOME/Desktop"; fi
      mkdir -p "$desk"

      # The primary monitor (else the first connected one): its index among the
      # active monitors, width and offset.
      read -r mi mw mx my < <(xrandr --current 2>/dev/null | awk '
        / connected/ && match($0, /[0-9]+x[0-9]+\+[0-9]+\+[0-9]+/) {
          split(substr($0, RSTART, RLENGTH), g, /[x+]/)
          line = (n + 0) " " g[1] " " g[3] " " g[4]; n++
          if (/ connected primary/) { print line; found = 1; exit }
          if (first == "") first = line
        }
        END { if (!found && first != "") print first }') || true

      # Nemo auto-arranges the desktop (one column from the top left) unless the
      # desktop folder says otherwise, and then ignores stored positions. Turn it
      # off for the primary monitor; right-click > Auto-arrange turns it back on.
      metadata="''${XDG_CONFIG_HOME:-$HOME/.config}/nemo/desktop-metadata"
      if [ -n "''${mi:-}" ] && ! grep -qs "^\[desktop-monitor-$mi\]" "$metadata"; then
        mkdir -p "$(dirname "$metadata")"
        printf '[desktop-monitor-%s]\nnemo-icon-view-auto-layout=false\n\n' "$mi" >> "$metadata"
      fi

      launchers=(${lib.escapeShellArgs cfg.topRightLaunchers})
      row=0
      for launcher in "''${launchers[@]}"; do
        target="$desk/$(basename "$launcher")"
        [ -e "$launcher" ] && [ ! -e "$target" ] || continue
        install -m755 "$launcher" "$target"
        if [ -n "''${mw:-}" ]; then
          gio set "$target" metadata::nemo-icon-position \
            "$((mx + mw - ${toString cell.right})),$((my + ${toString cell.top} + row * ${toString cell.height}))" || true
          # With its monitor recorded Nemo takes the position as it is; without,
          # it snaps the icon to a free cell, and counts the icon's own cell as taken.
          gio set "$target" metadata::monitor "$mi" || true
        fi
        row=$((row + 1))
      done

      mkdir -p "$(dirname "$stamp")"
      touch "$stamp"
    '';
  };
  # Where the launchers go, in desktop pixels at the default icon size: mirroring
  # Computer in the top-left corner, then 100 px (one row) apart.
  cell = {
    height = 100;
    right = 146;
    top = 22;
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

    topRightLaunchers = lib.mkOption {
      type = lib.types.listOf lib.types.path;
      default = lib.optional (
        config.services.starah.enable && config.services.starah.session.enable
      ) "${config.services.starah.session.package}/share/applications/org.starah.Session.desktop";
      defaultText = lib.literalMD "Starah's Agent Privileges, when Starah's session app is on";
      description = ''
        Launchers (.desktop files) put on each user's desktop at their first
        login, in the top-right corner, one below the other. Users can move or
        delete them; they are not put back.
      '';
    };

    browser = {
      package = lib.mkOption {
        type = lib.types.nullOr lib.types.package;
        default = pkgs.brave-origin;
        defaultText = lib.literalExpression "pkgs.brave-origin";
        description = ''
          The web browser that comes with the desktop (also on the live USB), set
          as the default browser and put in the panel's launchers. Brave Origin:
          Brave without Rewards, Wallet, VPN or AI. null: no browser.
        '';
      };
      desktopFile = lib.mkOption {
        type = lib.types.str;
        default = "brave-origin.desktop";
        description = "The browser's menu entry (.desktop file name).";
      };
    };

    panelLaunchers = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [
        "nemo.desktop"
      ]
      ++ lib.optional (cfg.browser.package != null) cfg.browser.desktopFile
      ++ [ "org.gnome.Terminal.desktop" ];
      defaultText = lib.literalMD "Files, the browser (`browser.desktopFile`) and Terminal";
      description = ''
        Menu entries (.desktop file names) in the panel's launchers, next to the
        start button, for each user's first session. Users can change them (right
        click > Configure); a user's own list is never replaced.
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

    # First login: launchers in the desktop's top-right corner (Starah's Agent
    # Privileges by default). Initialization runs before nemo-desktop starts.
    environment.etc."xdg/autostart/ocimum-desktop-defaults.desktop" =
      lib.mkIf (cfg.topRightLaunchers != [ ])
        {
          text = ''
            [Desktop Entry]
            Type=Application
            Name=Ocimum Desktop defaults
            Exec=${lib.getExe desktopDefaults}
            OnlyShowIn=X-Cinnamon;
            NoDisplay=true
            X-GNOME-Autostart-Phase=Initialization
            X-GNOME-AutoRestart=false
          '';
        };

    # The browser: installed, and opening web links.
    environment.systemPackages = lib.optional (cfg.browser.package != null) cfg.browser.package;
    xdg.mime.defaultApplications = lib.mkIf (cfg.browser.package != null) (
      lib.genAttrs [
        "text/html"
        "application/xhtml+xml"
        "x-scheme-handler/http"
        "x-scheme-handler/https"
      ] (_: lib.mkDefault cfg.browser.desktopFile)
    );

    # System Settings → Backgrounds lists the Ocimum wallpapers from here.
    environment.pathsToLink = [
      "/share/backgrounds"
      "/share/cinnamon-background-properties"
    ];

    # Mint-Y-Dark, the Tulsi Leaf wallpaper and the TulsiOS start button as defaults.
    # The panel is the fork's default plus Show Desktop and Panel Launchers on the
    # left and Trash on the right; the desktop shows Computer, Home, Trash and drives.
    services.xserver.desktopManager.cinnamon.extraGSettingsOverrides = ''
      [org.cinnamon]
      app-menu-icon-name='${startIcons.${cfg.startIcon}}'
      enabled-applets=${enabledApplets}
      # The launchers applet imports this list into its own settings on a user's
      # first session, then marks it DEPRECATED (Cinnamon's upgrade path from the
      # old key): a default for new users that never replaces a user's own list.
      panel-launchers=[${lib.concatMapStringsSep ", " (l: "'${l}'") cfg.panelLaunchers}]

      [org.nemo.desktop]
      show-desktop-icons=true
      computer-icon-visible=true
      home-icon-visible=true
      trash-icon-visible=true
      volumes-visible=true

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
