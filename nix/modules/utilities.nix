# tulsi.utilities: everyday tools on every TulsiOS desktop.
#
# - LocalSend: sends files and text to phones and computers on the same network
#   (Android, iPhone, Windows, macOS, Linux), without an account or the internet.
#   Its firewall ports (TCP and UDP 53317) are open: other devices can't find this
#   one otherwise. Turn it off with `programs.localsend.enable = false;`.
#
# Tailscale isn't installed by default: `tulsi service enable tailscale` starts it,
# then `tailscale up` signs in (the TulsiOS Wiki's "Sharing files and networks").
{
  config,
  lib,
  ...
}:

{
  options.tulsi.utilities.enable = lib.mkOption {
    type = lib.types.bool;
    default =
      (config.ocimum.desktop.enable || config.sonic.desktop.enable || config.tulsi.dwm.enable)
      && !config.tulsi.installer.enable;
    defaultText = lib.literalMD "on with any TulsiOS desktop, except the live installer";
    description = "Everyday tools on the desktop: LocalSend.";
  };

  config = lib.mkIf config.tulsi.utilities.enable {
    programs.localsend.enable = lib.mkDefault true;
  };
}
