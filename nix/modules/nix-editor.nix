# ocimum.nixEditor — Nix Editor (ADR 0019): a way to package software yourself when
# neither a TulsiOS package, a Recipe nor an AI model helps. On by default on the
# Ocimum desktop; the install window's "Edit It Yourself" opens Recipe drafts in it.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.ocimum.nixEditor;
in
{
  options.ocimum.nixEditor = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = config.ocimum.desktop.enable;
      defaultText = lib.literalExpression "config.ocimum.desktop.enable";
      description = "Nix Editor, with nixd and a Nix guide.";
    };

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ../packages/ocimum-nix-editor.nix { };
      defaultText = lib.literalExpression "pkgs.callPackage ../packages/ocimum-nix-editor.nix { }";
      description = "The Nix Editor package.";
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ cfg.package ];
    xdg.mime.enable = true;
    xdg.mime.defaultApplications."text/x-nix" = lib.mkDefault "org.tulsi.NixEditor.desktop";
  };
}
