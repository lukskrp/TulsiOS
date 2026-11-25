# ocimum.themes: Themes (ADR 0021). tulsi-theme switches the desktop's colours and
# background from a palette, per person and at once (no rebuild); the Themes app
# shows the palettes. On by default on each TulsiOS desktop.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.ocimum.themes;
in
{
  options.ocimum.themes = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = config.ocimum.desktop.enable || config.sonic.desktop.enable || config.tulsi.dwm.enable;
      defaultText = lib.literalExpression "config.ocimum.desktop.enable || config.sonic.desktop.enable || config.tulsi.dwm.enable";
      description = "Themes from palettes: the tulsi-theme command and the Themes app.";
    };

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ../packages/ocimum-themes.nix { };
      defaultText = lib.literalExpression "pkgs.callPackage ../packages/ocimum-themes.nix { }";
      description = "The Themes package.";
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [
      cfg.package
      # Every Mint-Y icon colour, which a palette's accent picks from.
      pkgs.mint-y-icons
    ];
    # Stock palettes under /run/current-system/sw/share/tulsi/themes, for agents
    # and people to read and copy.
    environment.pathsToLink = [ "/share/tulsi" ];
    programs.dconf.enable = true;
  };
}
