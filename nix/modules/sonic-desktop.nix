# sonic.desktop — SonicDE, the KDE Plasma 6 fork that keeps X11 (ADR 0020).
#
# The packages are tulsipkgs' `sonicPackages` (Sonic's frameworks, Plasma 6.8 and
# apps). nixpkgs' plasma6 module is Wayland-only since Plasma 6.8, so this is its
# X11 counterpart: the same services, on XLibre, logging in through the Ocimum
# Greeter like the other TulsiOS desktops, with TulsiOS's own apps and defaults.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.sonic.desktop;
  sonic = cfg.packages;
  defaults = pkgs.callPackage ../packages/sonic-tulsi-defaults.nix { inherit (cfg.packages) silver; };
in
{
  options.sonic.desktop = {
    enable = lib.mkEnableOption "SonicDE, a KDE-style desktop on X11";

    packages = lib.mkOption {
      type = lib.types.attrs;
      default = pkgs.sonicPackages;
      defaultText = lib.literalExpression "pkgs.sonicPackages";
      description = "The SonicDE package set.";
    };

    autoLoginUser = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "User to log in automatically, or null for the greeter.";
    };

    browser = lib.mkOption {
      type = lib.types.nullOr lib.types.package;
      default = config.ocimum.desktop.browser.package;
      defaultText = lib.literalExpression "config.ocimum.desktop.browser.package";
      description = "The web browser that comes with the desktop (Brave Origin, as on Ocimum).";
    };
  };

  config = lib.mkIf cfg.enable {
    # KDE apps on this machine (the Software Center, `tulsi install
    # kdePackages.kate`) are built on Sonic's frameworks, as the desktop is: one
    # copy of each KDE library in a session, and apps that keep X11.
    nixpkgs.overlays = [ (final: _prev: { kdePackages = final.sonicPackages; }) ];

    services.xserver.enable = true;
    services.libinput.enable = lib.mkDefault true;
    qt.enable = true;

    # Login: the Ocimum Greeter (ADR 0010), on XLibre; the SonicDE X11 session.
    ocimum.greeter.enable = true;
    services.displayManager = {
      sessionPackages = [ sonic.plasma-workspace.sessions ];
      defaultSession = lib.mkDefault "sonicde";
      autoLogin = lib.mkIf (cfg.autoLoginUser != null) {
        enable = true;
        user = cfg.autoLoginUser;
      };
    };

    # TulsiOS on SonicDE as on Ocimum: Starah, the TulsiOS way of installing
    # software, the Nix Editor, and the browser.
    services.starah.enable = lib.mkDefault true;
    tulsi.adopt.enable = lib.mkDefault config.ocimum.softwareCenter.enable;
    ocimum.nixEditor.enable = lib.mkDefault true;

    environment.systemPackages =
      with sonic;
      [
        qtsvg
        qtimageformats

        # Frameworks with globally loadable bits.
        frameworkintegration
        kauth
        kcoreaddons
        kded
        kfilemetadata
        kguiaddons
        kiconthemes
        kimageformats
        kio
        kio-extras
        kio-fuse
        knighttime
        kpackage
        kservice
        kwallet
        kwallet-pam
        plasma-activities
        solid

        # The desktop: sonic-win (X11), the workspace and panel, settings, lock screen.
        kwin
        kscreen
        libkscreen
        kscreenlocker
        kactivitymanagerd
        kde-cli-tools
        kglobalacceld
        kwrited
        baloo
        milou
        polkit-kde-agent-1
        plasma-desktop
        plasma-workspace
        drkonqi
        libplasma
        plasma-integration
        kde-gtk-config
        kdeplasma-addons
        kmenuedit
        kinfocenter
        ksystemstats
        libksysguard
        systemsettings
        kcmutils
        kgamma
        powerdevil
        plasma-nm
        plasma-pa

        # Silver: Sonic's style and decoration; Breeze and its icons underneath.
        silver
        breeze
        breeze-icons
        breeze-gtk
        ocean-sound-theme
        qqc2-breeze-style
        qqc2-desktop-style
        plasma-workspace-wallpapers
        pkgs.hicolor-icon-theme
        pkgs.xdg-user-dirs

        # Apps: Ecco (files), Sonic Terminal, System Monitor, Screenies (screenshots).
        dolphin
        konsole
        plasma-systemmonitor
        spectacle
        kconfig # xdg-terminal from xdg-utils
        (lib.getBin qttools) # qdbus

        defaults
      ]
      ++ lib.optional (cfg.browser != null) cfg.browser
      ++ lib.optionals config.hardware.bluetooth.enable [
        bluedevil
        bluez-qt
      ]
      ++ lib.optional config.services.printing.enable print-manager;

    # The browser opens web links, as on Ocimum.
    xdg.mime.enable = true;
    xdg.mime.defaultApplications = lib.mkIf (cfg.browser != null) (
      lib.genAttrs [
        "text/html"
        "application/xhtml+xml"
        "x-scheme-handler/http"
        "x-scheme-handler/https"
      ] (_: lib.mkDefault config.ocimum.desktop.browser.desktopFile)
    );

    environment.pathsToLink = [
      "/share"
      "/libexec"
    ];
    environment.etc."X11/xkb".source = config.services.xserver.xkb.dir;
    environment.sessionVariables = {
      XDG_CONFIG_DIRS = [ "$HOME/.config/kdedefaults" ];
      KPACKAGE_DEP_RESOLVERS_PATH = "${sonic.frameworkintegration.out}/libexec/kf6/kpackagehandlers";
    };

    programs.gdk-pixbuf.modulePackages = [ pkgs.librsvg ];
    fonts.packages = [
      pkgs.noto-fonts
      pkgs.hack-font
    ];
    fonts.fontconfig.defaultFonts = {
      monospace = [
        "Hack"
        "Noto Sans Mono"
      ];
      sansSerif = [ "Noto Sans" ];
      serif = [ "Noto Serif" ];
    };

    programs.ssh.askPassword = lib.mkDefault "${sonic.ksshaskpass.out}/bin/ksshaskpass";
    services.accounts-daemon.enable = true;
    systemd.services.accounts-daemon.serviceConfig.PrivateTmp = false;
    services.power-profiles-daemon.enable = lib.mkDefault true;
    programs.fuse.enable = true;
    services.udisks2.enable = true;
    services.upower.enable = config.powerManagement.enable;
    services.udev.packages = [
      pkgs.libmtp.out
      pkgs.media-player-info
    ];
    systemd.packages = [ sonic.drkonqi ];

    xdg.icons.enable = true;
    xdg.icons.fallbackCursorThemes = lib.mkDefault [ "breeze_cursors" ];
    xdg.portal = {
      enable = true;
      extraPortals = [
        sonic.kwallet
        sonic.xdg-desktop-portal-kde
        pkgs.xdg-desktop-portal-gtk
      ];
      configPackages = lib.mkDefault [ sonic.plasma-workspace ];
    };
    services.pipewire.enable = lib.mkDefault true;

    # The lock screen's PAM service, and KWallet unlocked at login.
    security.pam.services = {
      login.kwallet = {
        enable = true;
        package = sonic.kwallet-pam;
      };
      kde = {
        allowNullPassword = true;
        kwallet = {
          enable = true;
          package = sonic.kwallet-pam;
        };
        fprintAuth = false;
        p11Auth = false;
      };
    };

    security.wrappers = {
      ksystemstats_intel_helper = {
        owner = "root";
        group = "root";
        capabilities = "cap_perfmon+ep";
        source = "${sonic.ksystemstats}/libexec/ksystemstats_intel_helper";
      };
      ksgrd_network_helper = {
        owner = "root";
        group = "root";
        capabilities = "cap_net_raw+ep";
        source = "${sonic.libksysguard}/libexec/ksysguard/ksgrd_network_helper";
      };
    };

    programs.dconf.enable = true;
    programs.chromium = {
      enablePlasmaBrowserIntegration = true;
      plasmaBrowserIntegrationPackage = sonic.plasma-browser-integration;
    };

    # KDE's per-user service cache refers to store paths; rebuilt after a change.
    system.userActivationScripts.sonic-ksycoca = {
      text = ''rm -fv "''${XDG_CACHE_HOME:-$HOME/.cache}/ksycoca"*'';
    };
  };
}
