# tulsi.daemon — the privileged TulsiOS system daemon (Phase 2).
#
# Will own /etc/nixos/tulsi/state.json, expose the D-Bus API
# org.tulsi.Manager1, gate changes through polkit and run
# eval -> dry-build -> switch, committing every change to git.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.tulsi.daemon;
in
{
  options.tulsi.daemon = {
    enable = lib.mkEnableOption "tulsid, the TulsiOS system daemon (Phase 2, not functional yet)";
    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ../packages/tulsi-tools.nix { };
      defaultText = lib.literalExpression "pkgs.callPackage ../packages/tulsi-tools.nix { }";
      description = "Package providing tulsid, tulsi and tulsi-mcp.";
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ cfg.package ];
    # TODO(phase-2): systemd service, D-Bus policy, polkit actions.
  };
}
