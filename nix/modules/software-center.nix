# ocimum.softwareCenter — GUI to install and remove software through tulsid.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.ocimum.softwareCenter;
in
{
  options.ocimum.softwareCenter = {
    enable = lib.mkEnableOption "the Ocimum Software Center";

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ../packages/ocimum-software-center.nix { };
      defaultText = lib.literalExpression "pkgs.callPackage ../packages/ocimum-software-center.nix { }";
      description = "The Ocimum Software Center package.";
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = config.tulsi.daemon.enable;
        message = "ocimum.softwareCenter requires tulsi.daemon.enable = true.";
      }
    ];
    environment.systemPackages = [ cfg.package ];
  };
}
