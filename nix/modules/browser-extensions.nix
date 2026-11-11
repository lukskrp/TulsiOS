# tulsi.browserExtensions — browser extensions become declarative automatically.
#
# adopt (default on with tulsid): the `tulsi-extwatch` user service watches
# Firefox and Chromium-family profiles. When the user installs an extension
# from addons.mozilla.org or the Chrome Web Store, it shows a notice ("will be
# installed declaratively") and adds the extension to tulsi.state, whose
# browser policies then install and own it. See docs/adr/0007.
#
# blockImperativeInstalls (default off) forbids browser-initiated installs
# entirely; extensions then only come from tulsi.state (CLI, Software Center).
# It disables adoption, since there is nothing left to adopt.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.tulsi.browserExtensions;
  adopting = cfg.adopt.enable && !cfg.blockImperativeInstalls;
in
{
  options.tulsi.browserExtensions = {
    adopt = {
      enable = lib.mkOption {
        type = lib.types.bool;
        default = config.tulsi.daemon.enable;
        defaultText = lib.literalExpression "config.tulsi.daemon.enable";
        description = "Adopt store-installed browser extensions into tulsi.state automatically.";
      };

      withoutPassword = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = ''
          Let active local users add or remove browser extensions (and only
          those) without a password, so adoption is seamless. Extensions apply
          to all users of the machine.
        '';
      };

      grace = lib.mkOption {
        type = lib.types.ints.unsigned;
        default = 8;
        description = "Seconds the \"Keep it imperative\" button stays usable before adoption.";
      };
    };

    blockImperativeInstalls = lib.mkEnableOption ''
      blocking browser-initiated extension installs, so extensions can only
      come from tulsi.state. Disables adoption
    '';

    blockedMessage = lib.mkOption {
      type = lib.types.str;
      default = "On TulsiOS, extensions are installed declaratively. Use the Software Center or `tulsi ext add`.";
      description = "Message Firefox shows when a blocked install is attempted.";
    };
  };

  config = lib.mkMerge [
    (lib.mkIf cfg.blockImperativeInstalls {
      programs.firefox.policies.ExtensionSettings."*" = {
        installation_mode = "blocked";
        blocked_install_message = cfg.blockedMessage;
      };
      programs.chromium.extraOpts.ExtensionInstallBlocklist = [ "*" ];
    })

    (lib.mkIf adopting {
      assertions = [
        {
          assertion = config.tulsi.daemon.enable;
          message = "tulsi.browserExtensions.adopt requires tulsi.daemon.enable = true.";
        }
      ];

      systemd.user.services.tulsi-extwatch = {
        description = "TulsiOS: install browser extensions declaratively";
        wantedBy = [ "graphical-session.target" ];
        partOf = [ "graphical-session.target" ];
        after = [ "graphical-session.target" ];
        serviceConfig = {
          ExecStart = "${config.tulsi.daemon.package}/bin/tulsi-extwatch --grace ${toString cfg.adopt.grace}";
          Restart = "on-failure";
          RestartSec = 5;
        };
      };

      security.polkit.extraConfig = lib.mkIf cfg.adopt.withoutPassword ''
        polkit.addRule(function (action, subject) {
          if (action.id === "org.tulsi.extensions" && subject.local && subject.active)
            return polkit.Result.YES;
          return polkit.Result.NOT_HANDLED;
        });
      '';
    })
  ];
}
