# ADR 0037: the file manager's quick actions make new files beside the originals
# and leave them as they were; the Nemo actions and KDE service menus are installed.
{ self }:
{
  name = "file-actions";

  nodes.machine =
    { pkgs, modulesPath, ... }:
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      tulsi.fileActions.enable = true;
      # To make test pictures and sounds.
      environment.systemPackages = [ pkgs.imagemagick pkgs.ffmpeg ];
    };

  testScript = ''
    machine.wait_for_unit("multi-user.target")

    def alice(cmd):
        return machine.succeed(f"su - alice -c '{cmd}'")

    with subtest("the right-click actions are installed"):
        for action in ["tulsi-explain", "tulsi-localsend", "tulsi-resize", "tulsi-to-mp3", "tulsi-doc-to-pdf"]:
            machine.succeed(f"test -e /run/current-system/sw/share/nemo/actions/{action}.nemo_action")
        machine.succeed("test -e /run/current-system/sw/share/kio/servicemenus/tulsi-file-tools-images.desktop")

    with subtest("resize makes a smaller copy and keeps the original"):
        alice("magick -size 400x300 xc:red photo.jpg")
        out = alice("tulsi-file-tools resize --width 100 --no-window photo.jpg").strip()
        assert out == "/home/alice/photo (resized).jpg", out
        assert alice("magick identify -format %w \"photo (resized).jpg\"").strip() == "100"
        assert alice("magick identify -format %w photo.jpg").strip() == "400"
        # Again: a new name, never an overwrite.
        out = alice("tulsi-file-tools resize --percent 50 --no-window photo.jpg").strip()
        assert out == "/home/alice/photo (resized 2).jpg", out

    with subtest("images become JPG, PNG and one PDF"):
        alice("magick -size 50x50 xc:none -fill blue -draw \"circle 25,25 25,5\" logo.png")
        assert alice("tulsi-file-tools to-jpg --no-window logo.png").strip() == "/home/alice/logo.jpg"
        alice("tulsi-file-tools images-to-pdf --no-window photo.jpg logo.png")
        alice("head -c 5 photo.pdf | grep -q %PDF")

    with subtest("audio and video become MP3"):
        alice("ffmpeg -loglevel error -f lavfi -i sine=duration=1 tone.wav")
        alice("tulsi-file-tools to-mp3 --no-window tone.wav")
        alice("test -s tone.mp3 && test -s tone.wav")

    with subtest("documents without LibreOffice: a clear message, no file"):
        alice("echo hi > letter.odt")
        out = machine.fail("su - alice -c 'tulsi-file-tools doc-to-pdf --no-window letter.odt 2>&1'")
        assert "LibreOffice" in out, out
        machine.fail("test -e /home/alice/letter.pdf")
  '';
}
