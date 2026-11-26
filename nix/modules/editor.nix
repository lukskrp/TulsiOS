# tulsi.editor: Fresh is the editor in terminals (ADR 0031).
#
# Fresh (getfresh.dev) is a terminal editor with ordinary keys (Ctrl+S saves,
# Ctrl+Q quits, Ctrl+P opens files and commands), a mouse and menus. It is
# EDITOR and VISUAL for everyone, so git, crontab -e, `starah rules edit` and
# `sudoedit` open it; nano is not installed. To change a system file, use
# `sudoedit FILE`: Fresh then runs as you, and sudo writes the file back.
#
# Double-clicked text files still open the desktop's own editor (xed on Ocimum).
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.tulsi.editor;
in
{
  options.tulsi.editor = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Fresh as the terminal editor (EDITOR, VISUAL), instead of nano.";
    };
    package = lib.mkPackageOption pkgs "fresh-editor" { };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ cfg.package ];
    # Above NixOS's own `mkDefault "nano"`, as programs.vim.defaultEditor does.
    environment.sessionVariables = {
      EDITOR = lib.mkOverride 900 cfg.package.meta.mainProgram;
      VISUAL = lib.mkOverride 900 cfg.package.meta.mainProgram;
    };
    programs.nano.enable = lib.mkDefault false;
    # Fresh's app-menu entry offers it for text files; the desktop's editor stays
    # the default for double-clicks.
    xdg.mime.defaultApplications."text/plain" = lib.mkIf config.ocimum.desktop.enable (
      lib.mkDefault "org.x.editor.desktop"
    );
  };
}
