# The Nix Editor (ADR 0019) on X11, offline: nixd suggests package names from the
# system's pinned nixpkgs, the guide follows the cursor, and nixd's problems and
# TulsiOS's own rules for local packages are marked. Screenshots land in the output.
{ self }:
{
  name = "nix-editor";

  nodes.machine =
    { pkgs, modulesPath, ... }:
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/x11.nix")
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      test-support.displayManager.auto.user = "alice";
      virtualisation.memorySize = 3072;
      nix.settings.substituters = pkgs.lib.mkForce [ ];

      ocimum.nixEditor.enable = true;
      environment.systemPackages = [
        (pkgs.callPackage ../packages/tulsi-tools.nix { })
        pkgs.xdotool
        pkgs.xprop
        # Themes as on the Ocimum desktop, switched live over XSETTINGS as Cinnamon's
        # settings daemon does when Themes changes them.
        pkgs.mint-themes
        pkgs.xsettingsd
      ];
      environment.pathsToLink = [ "/share/themes" ];
    };

  testScript = ''
    from datetime import timedelta

    machine.wait_for_x()
    machine.wait_until_succeeds("pgrep -u alice -o icewm", timeout=timedelta(minutes=5))
    wm = machine.succeed("pgrep -u alice -o icewm").strip()
    session = dict(
        line.split("=", 1)
        for line in machine.succeed(f"tr '\\0' '\\n' < /proc/{wm}/environ").splitlines()
        if "=" in line
    )
    env = " ".join(
        f"{k}={session[k]}"
        for k in ["DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS"]
        if k in session
    )

    def alice(cmd):
        return f"su - alice -c '{env} {cmd}'"

    def logged(pattern, timeout=90):
        try:
            machine.wait_until_succeeds(f"grep -qE -- {pattern!r} /tmp/editor.log", timeout=timeout)
        except Exception:
            machine.execute("tail -n 60 /tmp/editor.log >&2")
            machine.screenshot("nix-editor-failed")
            raise

    def keys(*names):
        for k in names:
            machine.send_key(k)

    machine.succeed(
        "mkdir -p /home/alice/demo && cat > /home/alice/demo/package.nix <<'EOF'\n"
        "{ lib, stdenv, pkgs }:\n"
        "stdenv.mkDerivation {\n"
        "  pname = \"demo\";\n"
        "  version = \"1.0\";\n"
        "  src = ./demo;\n"
        "  buildInputs = [ ];\n"
        "}\n"
        "EOF\n"
        "chown -R alice /home/alice/demo"
    )

    with subtest("the editor opens a package with nixd, offline, and the guide beside it"):
        machine.succeed(alice("ocimum-nix-editor /home/alice/demo/package.nix >/tmp/editor.log 2>&1 &"))
        machine.wait_until_succeeds(
            alice("xwininfo -root -tree 2>/dev/null") + " | grep -qF 'Nix Editor'", timeout=60)
        logged("lsp: ready")
        logged("guide: start")
        # Its own icon, in the menu and on the window.
        machine.succeed("test -f /run/current-system/sw/share/icons/hicolor/scalable/apps/org.tulsi.NixEditor.svg")
        machine.succeed("grep -qx 'Icon=org.tulsi.NixEditor' /run/current-system/sw/share/applications/org.tulsi.NixEditor.desktop")
        win = machine.succeed(alice("xdotool search --name \"Nix Editor\"")).split()[0]
        machine.succeed(alice(f"xprop -id {win} _NET_WM_ICON") + " | grep -q 'Icon ('")

    with subtest("problems: nixd's, and TulsiOS's rules for local packages"):
        logged("problem: nixd 1:3 attribute `lib` of argument is not used")
        logged("problem: tulsios path literals such as `./demo` are not allowed")

    with subtest("the guide explains the word under the cursor"):
        keys("ctrl-home", "down")
        for _ in range(10):
            machine.send_key("right")
        logged("guide: mkderivation")
        machine.sleep(1)
        machine.screenshot("nix-editor-guide")

    with subtest("completion offers the system's packages"):
        # Into `buildInputs = [ ];`, between the brackets.
        keys("ctrl-home", "down", "down", "down", "down", "down", "end", "left", "left")
        machine.send_chars("pkgs.hel")
        machine.send_key("ctrl-spc")
        logged("completion: [0-9]+ items for 'hel': .*\\bhello\\b")
        machine.sleep(1)
        machine.screenshot("nix-editor-completion")
        machine.send_key("esc")

    with subtest("a syntax error is marked as you type"):
        machine.send_chars(" = ")
        logged("problem: nixd 6:[0-9]+ (expected|unexpected)")
        machine.sleep(1)
        machine.screenshot("nix-editor-problems")

    def theme(name):
        machine.succeed(f"echo 'Net/ThemeName \"{name}\"' > /home/alice/.xsettingsd && chown alice /home/alice/.xsettingsd")
        machine.succeed("pkill -HUP -x xsettingsd")

    def last_scheme(scheme):
        try:
            machine.wait_until_succeeds(
                f"grep 'nix-editor: scheme:' /tmp/editor.log | tail -n 1 | grep -q '{scheme}'", timeout=30)
        except Exception:
            machine.execute("grep 'scheme:' /tmp/editor.log >&2")
            machine.screenshot("nix-editor-theme-failed")
            raise

    with subtest("the code's colours follow the desktop theme, dark and light, while open"):
        machine.succeed("echo 'Net/ThemeName \"Mint-Y\"' > /home/alice/.xsettingsd && chown alice /home/alice/.xsettingsd")
        machine.succeed(alice("xsettingsd >/tmp/xsettingsd.log 2>&1 &"))
        machine.wait_until_succeeds("pgrep -x xsettingsd", timeout=30)
        last_scheme("classic")
        theme("Mint-Y-Dark")
        last_scheme("oblivion")
        machine.sleep(2)
        machine.screenshot("nix-editor-dark")
        theme("Mint-Y")
        last_scheme("classic")
        machine.sleep(2)
        machine.screenshot("nix-editor-light")

    with subtest("saving writes the file and checks it again"):
        machine.send_key("ctrl-s")
        logged("saved /home/alice/demo/package.nix")
        machine.succeed("grep -q 'pkgs.hel = ' /home/alice/demo/package.nix")
  '';
}
