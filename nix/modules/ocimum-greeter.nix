# ocimum.greeter — TulsiOS's login screen (ADR 0010).
#
# greetd runs on VT1. Its greeter is the Ocimum Greeter (apps/ocimum-greeter, OTK)
# inside an X server of its own: XLibre, run as the unprivileged `greeter` user through
# logind. After a login, the session gets a fresh XLibre server running as the user
# (`ocimum-x-session`), started like every NixOS display manager starts X sessions:
# through services.displayManager.sessionData.wrapper.
#
# No LightDM, SDDM or GDM: GDM 51 can only show its login screen on Wayland.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.ocimum.greeter;
  dm = config.services.displayManager;
  xdm = config.services.xserver.displayManager;

  sessionsDir = "${dm.sessionData.desktops}/share/xsessions";
  defaultSession = if dm.defaultSession != null then dm.defaultSession else dm.sessionData.autologinSession;

  # The display manager's X arguments (-config, -xkbdir, …) without the display
  # number and -terminate: the launchers pass `:0` first, where xinit expects it.
  xserverArgs = lib.filter (
    arg: arg != "-terminate" && !(lib.hasPrefix ":" arg)
  ) xdm.xserverArgs;

  toolPath = lib.makeBinPath [
    pkgs.xinit
    pkgs.xauth
    pkgs.util-linux # mcookie
    pkgs.coreutils
    pkgs.gnugrep
    pkgs.gnused
  ];

  # Creates an X cookie in the session's runtime directory and runs `xinit CLIENT…`
  # with an XLibre server on VT `vt` (the logind session's), as the calling user.
  startX = ''
    runtime="''${XDG_RUNTIME_DIR:-}"
    if [ -z "$runtime" ] || [ ! -w "$runtime" ]; then runtime=$(mktemp -d); fi
    export XAUTHORITY="$runtime/ocimum-xauthority"
    rm -f "$XAUTHORITY"
    touch "$XAUTHORITY"
    chmod 600 "$XAUTHORITY"
    xauth -q -f "$XAUTHORITY" add :0 . "$(mcookie)"
    x_server() {
      echo "${pkgs.xorg-server}/bin/X" :0 "vt''${XDG_VTNR:-1}" -keeptty -auth "$XAUTHORITY" ${lib.escapeShellArgs xserverArgs}
    }
  '';

  greeterConfig = pkgs.writeText "ocimum-greeter.json" (
    builtins.toJSON {
      sessions_dir = sessionsDir;
      default_session = defaultSession;
      launcher = lib.getExe sessionLauncher;
      wallpaper = cfg.wallpaper;
      state_dir = "/var/cache/ocimum-greeter";
      title = cfg.title;
    }
  );

  # greetd's default_session: the greeter in its own XLibre server.
  greeterLauncher = pkgs.writeShellScript "ocimum-greeter-x" ''
    set -eu
    export PATH=${toolPath}:/run/current-system/sw/bin
    ${startX}
    export GTK_THEME=${lib.escapeShellArg cfg.theme}
    export XDG_DATA_DIRS=${lib.makeSearchPath "share" cfg.themePackages}''${XDG_DATA_DIRS:+:$XDG_DATA_DIRS}
    # greetd does not keep the greeter's output: send it (and X's) to the journal.
    exec systemd-cat -t ocimum-greeter xinit ${lib.getExe cfg.package} --config ${greeterConfig} -- $(x_server)
  '';

  # Starts an X session for the logged-in user: `ocimum-x-session EXEC` (from the
  # greeter, with the session's Exec line) or `ocimum-x-session --session NAME`
  # (autologin: Exec and desktop names are read from NAME.desktop).
  sessionLauncher = pkgs.writeShellScriptBin "ocimum-x-session" ''
    set -eu
    # The session keeps the login PATH (from /etc/profile: the setuid wrappers
    # such as pkexec and sudo, the user's profiles); these tools are for this
    # script only. /etc/profile does not set PATH a second time.
    login_path=''${PATH:-/run/current-system/sw/bin}
    case ":$login_path:" in
      *:/run/wrappers/bin:*) ;;
      *) login_path=/run/wrappers/bin:$login_path ;;
    esac
    export PATH=${toolPath}:/run/current-system/sw/bin
    if [ "''${1:-}" = "--session" ]; then
      file=${sessionsDir}/"$2".desktop
      exec_line=$(grep -m1 '^Exec=' "$file" | cut -d= -f2-)
      names=$(grep -m1 '^DesktopNames=' "$file" | cut -d= -f2- | sed 's/;$//; s/;/:/g' || true)
      export XDG_SESSION_TYPE=x11 XDG_SESSION_DESKTOP="$2"
      if [ -n "$names" ]; then export XDG_CURRENT_DESKTOP="$names"; fi
      set -- "$exec_line"
    fi
    ${startX}
    server=$(x_server)
    export PATH="$login_path"
    exec ${config.systemd.package}/bin/systemd-cat -t ocimum-x-session \
      ${pkgs.xinit}/bin/xinit ${dm.sessionData.wrapper} "$@" -- $server
  '';
in
{
  options.ocimum.greeter = {
    enable = lib.mkEnableOption "the Ocimum Greeter (greetd) as the login screen";

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ../packages/ocimum-greeter.nix { };
      defaultText = lib.literalExpression "pkgs.callPackage ../packages/ocimum-greeter.nix { }";
      description = "The Ocimum Greeter package.";
    };

    title = lib.mkOption {
      type = lib.types.str;
      default = "TulsiOS";
      description = "Heading of the login screen.";
    };

    wallpaper = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = null;
      description = "Background of the login screen.";
    };

    theme = lib.mkOption {
      type = lib.types.str;
      default = "Mint-Y-Dark";
      description = "GTK 3 theme of the login screen (OTK shares GTK 3's themes).";
    };

    themePackages = lib.mkOption {
      type = lib.types.listOf lib.types.package;
      default = [
        pkgs.mint-themes
        pkgs.mint-y-icons
        pkgs.adwaita-icon-theme
        pkgs.hicolor-icon-theme
      ];
      defaultText = lib.literalExpression "[ pkgs.mint-themes pkgs.mint-y-icons pkgs.adwaita-icon-theme pkgs.hicolor-icon-theme ]";
      description = "Packages providing the theme and icons the greeter uses.";
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = !(xdm.lightdm.enable || dm.sddm.enable || dm.gdm.enable);
        message = "ocimum.greeter is TulsiOS's login screen; disable LightDM, SDDM and GDM.";
      }
      {
        assertion = defaultSession != null;
        message = "ocimum.greeter needs an X session (services.displayManager.defaultSession).";
      }
    ];

    services.greetd = {
      enable = true;
      settings = {
        default_session.command = "${greeterLauncher}";
        initial_session = lib.mkIf dm.autoLogin.enable {
          user = dm.autoLogin.user;
          command = "${lib.getExe sessionLauncher} --session ${defaultSession}";
        };
      };
    };

    # The X servers run as the session's user; logind hands them the devices.
    environment.systemPackages = [ sessionLauncher ];

    # The greeter remembers who logged in last.
    systemd.tmpfiles.rules = [ "d /var/cache/ocimum-greeter 0750 greeter greeter - -" ];
  };
}
