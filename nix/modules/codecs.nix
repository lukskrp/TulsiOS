# tulsi.codecs and tulsi.fonts.microsoft: media that plays, files that open
# (ADR 0035).
#
# Video and music in Celluloid (mpv) already play from nixpkgs' ffmpeg. The
# codecs here are for everything else:
# - GStreamer's plugin sets for the whole system. NixOS has no option for that,
#   so they go in the system profile and GST_PLUGIN_SYSTEM_PATH_1_0 points there.
#   Apps that use GStreamer (Rhythmbox, Elisa, the browser's media, …) then play
#   MP3, AAC, H.264 and the rest.
# - DVDs (libdvdcss), and RAR and 7z archives (unar, 7-Zip).
# The installer turns this on unless the person unticks it ("Media").
#
# Microsoft's fonts (Arial, Times New Roman, …) are unfree: a separate option, which
# needs unfree software turned on.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.tulsi.codecs;
  gst = pkgs.gst_all_1;
in
{
  options.tulsi.codecs.enable = lib.mkEnableOption ''
    the common media codecs (GStreamer good, bad, ugly and libav), DVD playback and
    RAR/7z archives'';

  options.tulsi.fonts.microsoft.enable = lib.mkEnableOption ''
    Microsoft's core fonts (Arial, Times New Roman, Verdana, …), so documents made
    on Windows look as intended; they are unfree'';

  config = lib.mkMerge [
    (lib.mkIf cfg.enable {
      environment.systemPackages = [
        # GStreamer's own core elements (filesrc, queue, …): the variable below
        # replaces the plugin folder GStreamer would otherwise use for them.
        gst.gstreamer.out
        gst.gst-plugins-base
        gst.gst-plugins-good
        gst.gst-plugins-bad
        gst.gst-plugins-ugly
        gst.gst-libav
        pkgs.libdvdcss
        pkgs.unar
        pkgs._7zz
      ];
      environment.pathsToLink = [ "/lib" ];
      environment.sessionVariables.GST_PLUGIN_SYSTEM_PATH_1_0 = [
        "/run/current-system/sw/lib/gstreamer-1.0"
      ];
    })

    (lib.mkIf config.tulsi.fonts.microsoft.enable {
      assertions = [
        {
          assertion = config.nixpkgs.config.allowUnfree or false;
          message = ''
            Microsoft's fonts are unfree: add `nixpkgs.config.allowUnfree = true;` to
            configuration.nix (the installer does this when they are ticked).'';
        }
      ];
      fonts.packages = [ pkgs.corefonts ];
    })
  ];
}
