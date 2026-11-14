# ocimum.assistant — the Ocimum Assistant chat window.
#
# Uses Claude (Anthropic API) by default, with tulsi-mcp as its only tool set:
# every change is shown in the ocimum-approve dialog before tulsid applies it.
# With Starah enabled, tulsi-mcp instead runs as the Starah agent `assistant`
# (its own sandboxed account), and Starah's level for it decides what it may do on
# its own; the rest waits for the human in Starah's Agent Request window.
# The API key is stored in the user's keyring from the app's Settings.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.ocimum.assistant;
in
{
  options.ocimum.assistant = {
    enable = lib.mkEnableOption "the Ocimum Assistant";

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ../packages/ocimum-assistant.nix { };
      defaultText = lib.literalExpression "pkgs.callPackage ../packages/ocimum-assistant.nix { }";
      description = "The Ocimum Assistant package.";
    };
  };

  config = lib.mkIf cfg.enable (lib.mkMerge [
    (lib.mkIf config.services.starah.enable {
      services.starah.agents.assistant = {
        level = lib.mkDefault 1;
        description = "Ocimum Assistant: installs software and edits the configuration through tulsi-mcp";
      };
      environment.sessionVariables.OCIMUM_ASSISTANT_MCP =
        "starah run --agent assistant -- tulsi-mcp --approval starah";
    })
    {
    assertions = [
      {
        assertion = config.tulsi.daemon.enable;
        message = "ocimum.assistant requires tulsi.daemon.enable = true.";
      }
    ];
    environment.systemPackages = [ cfg.package ];
    # Provides the ocimum-approve dialog that tulsi-mcp asks through.
    ocimum.softwareCenter.enable = lib.mkDefault true;
    # Where the API key is kept.
    services.gnome.gnome-keyring.enable = lib.mkDefault true;
    }
  ]);
}
