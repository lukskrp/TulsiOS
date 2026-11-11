# tulsi.browserExtensions — make browser extensions declarative-only.
#
# When enabled, users can no longer install extensions imperatively from the
# browser. Phase 4 adds the force-installed "Ocimum Bridge" extension that
# turns store "Add to browser" clicks into tulsi.state changes instead.
{ config, lib, ... }:

let
  cfg = config.tulsi.browserExtensions;
in
{
  options.tulsi.browserExtensions = {
    blockImperativeInstalls = lib.mkEnableOption ''
      blocking browser-initiated extension installs, so extensions can only
      come from tulsi.state (enable once the Ocimum Bridge ships, Phase 4)
    '';

    blockedMessage = lib.mkOption {
      type = lib.types.str;
      default = "On TulsiOS, extensions are installed declaratively. Use the Ocimum Software Center or the Ocimum Assistant.";
      description = "Message Firefox shows when a blocked install is attempted.";
    };
  };

  config = lib.mkIf cfg.blockImperativeInstalls {
    programs.firefox.policies.ExtensionSettings."*" = {
      installation_mode = "blocked";
      blocked_install_message = cfg.blockedMessage;
    };
    programs.chromium.extraOpts.ExtensionInstallBlocklist = [ "*" ];
  };
}
