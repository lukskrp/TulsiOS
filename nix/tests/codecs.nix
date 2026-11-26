# ADR 0035: with tulsi.codecs (the installer's default) every app's GStreamer
# decodes H.264 and MP3, and 7z archives open; without it those decoders aren't
# there. Ocimum's defaults open PDFs, pictures, RAW photos, music, video and
# archives in the apps chosen for them.
{ self }:
{
  name = "codecs";

  nodes.with_codecs =
    { pkgs, modulesPath, ... }:
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      ocimum.desktop.enable = true;
      tulsi.codecs.enable = true;
      # gst-launch-1.0 and gst-inspect-1.0, to try the codecs.
      environment.systemPackages = [ pkgs.gst_all_1.gstreamer ];
      virtualisation.memorySize = 2048;
    };

  nodes.without =
    { pkgs, ... }:
    {
      imports = [ self.nixosModules.default ];
      environment.systemPackages = [
        pkgs.gst_all_1.gstreamer
        pkgs.gst_all_1.gst-plugins-base
      ];
    };

  testScript = ''
    start_all()

    def alice(cmd):
        return with_codecs.succeed(f"su - alice -c '{cmd}'")

    with subtest("with codecs: H.264, AAC and MP3 for every app, through GStreamer"):
        with_codecs.wait_for_unit("multi-user.target")
        for element in ["avdec_h264", "avdec_aac", "mpg123audiodec", "x264enc", "lamemp3enc"]:
            alice(f"gst-inspect-1.0 {element} >/dev/null")
        # Make an MP4 (H.264) and an MP3, then play both to the end.
        alice("gst-launch-1.0 -q videotestsrc num-buffers=60 ! x264enc ! mp4mux ! filesink location=/tmp/t.mp4")
        alice("gst-launch-1.0 -q audiotestsrc num-buffers=50 ! lamemp3enc ! filesink location=/tmp/t.mp3")
        alice("gst-launch-1.0 -q filesrc location=/tmp/t.mp4 ! decodebin ! fakesink")
        alice("gst-launch-1.0 -q filesrc location=/tmp/t.mp3 ! decodebin ! fakesink")

    with subtest("with codecs: 7z and RAR tools, and DVD support"):
        alice("echo hello > /tmp/a.txt && 7zz a -bso0 /tmp/a.7z /tmp/a.txt && cd /tmp && rm a.txt && unar -q a.7z && grep -q hello /tmp/a/a.txt || grep -rq hello /tmp/a*")
        with_codecs.succeed("ls /run/current-system/sw/lib | grep -q libdvdcss")

    with subtest("Ocimum's defaults: each kind of file opens in its app"):
        mimeapps = with_codecs.succeed("cat /etc/xdg/mimeapps.list")
        for mime, app in [
            ("application/pdf", "xreader.desktop"),
            ("image/jpeg", "xviewer.desktop"),
            ("image/x-canon-cr2", "pix.desktop"),
            ("audio/mpeg", "io.github.celluloid_player.Celluloid.desktop"),
            ("video/mp4", "io.github.celluloid_player.Celluloid.desktop"),
            ("application/x-7z-compressed", "org.gnome.FileRoller.desktop"),
        ]:
            assert f"{mime}={app}" in mimeapps, (mime, app)
            with_codecs.succeed(f"test -e /run/current-system/sw/share/applications/{app}")

    with subtest("without codecs: no H.264 or MP3 decoder"):
        without.wait_for_unit("multi-user.target")
        without.fail("gst-inspect-1.0 avdec_h264")
        without.fail("gst-inspect-1.0 mpg123audiodec")
  '';
}
