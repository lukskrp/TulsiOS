# ocimum.gtk3o — graft GTK3-O into the whole system.
#
# Everything is built against stock nixpkgs gtk3 (binary cache stays usable),
# then `system.replaceDependencies` rewrites references to stock libgtk-3 so
# every GTK 3 program loads GTK3-O instead. Safe only because GTK3-O keeps the
# GTK 3.24 ABI (checked by gtk3-o's passthru.abiCheck).
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.ocimum.gtk3o;
in
{
  options.ocimum.gtk3o = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = config.ocimum.desktop.enable;
      defaultText = lib.literalExpression "config.ocimum.desktop.enable";
      description = "Replace GTK 3 system-wide with GTK3-O (by grafting, without rebuilding applications).";
    };

    package = lib.mkOption {
      type = lib.types.nullOr lib.types.package;
      default = null;
      description = "The GTK3-O build. Set by the TulsiOS flake's nixosModules.default.";
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = cfg.package != null;
        message = "ocimum.gtk3o.package is not set (use the TulsiOS flake's nixosModules.default).";
      }
      {
        assertion = cfg.package == null || cfg.package.name == pkgs.gtk3.name;
        message = "ocimum.gtk3o.package must have the same name as pkgs.gtk3 (${pkgs.gtk3.name}) to be grafted.";
      }
    ];

    system.replaceDependencies.replacements = [
      {
        oldDependency = pkgs.gtk3;
        newDependency = cfg.package;
      }
    ];
  };
}
