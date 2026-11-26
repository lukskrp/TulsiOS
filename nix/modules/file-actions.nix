# tulsi.fileActions: the file manager's right-click actions (ADR 0037), in Nemo
# (Ocimum) and Ecco/Dolphin (SonicDE):
# - Explain with Assistant: the Assistant gets the file's text in its question,
#   never the file itself (shown only when the Assistant is installed);
# - Send via LocalSend (when LocalSend is on);
# - Resize Images…, Convert to JPG/PNG, Combine into a PDF, Convert to MP3,
#   Convert to PDF (documents, when LibreOffice is installed).
# Conversions make a new file beside the original and never overwrite one. dwm has
# no file manager: there `tulsi-file-tools` works from a terminal.
{
  config,
  lib,
  pkgs,
  ...
}:

{
  options.tulsi.fileActions = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default =
        (config.ocimum.desktop.enable || config.sonic.desktop.enable || config.tulsi.dwm.enable)
        && !config.tulsi.installer.enable;
      defaultText = lib.literalMD "on with any TulsiOS desktop, except the live installer";
      description = "Right-click actions in the file manager: explain, send, resize and convert.";
    };
    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ../packages/tulsi-file-tools.nix { };
      defaultText = lib.literalExpression "pkgs.callPackage ../packages/tulsi-file-tools.nix { }";
      description = "The tulsi-file-tools package.";
    };
  };

  config = lib.mkIf config.tulsi.fileActions.enable {
    environment.systemPackages = [ config.tulsi.fileActions.package ];
    environment.pathsToLink = [
      "/share/nemo"
      "/share/kio"
    ];
  };
}
