# "Install it the TulsiOS way" (ADR 0013): apt and foreign binaries lead to
# tulsi-adopt; a downloaded tarball nobody packaged becomes a local package written
# by the Assistant (a scripted model here), built in Nix's sandbox by the Starah agent,
# approved by a person, added through tulsid, and undoable.
{ self }:
let
  # The "downloaded" software: a reproducible tarball with a tiny program.
  frobTarball =
    pkgs:
    pkgs.runCommand "frob-1.0.tar.gz" { } ''
      mkdir frob-1.0
      printf '#!/bin/sh\necho "frob 1.0"\n' > frob-1.0/frob
      chmod +x frob-1.0/frob
      tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -cf - frob-1.0 | gzip -n > $out
    '';
in
{
  name = "adopt";

  nodes.machine =
    { pkgs, modulesPath, ... }:
    let
      tarball = frobTarball pkgs;
      # Same path `nix-store --add-fixed sha256` gives the file (flat sha256, same name).
      hash = builtins.convertHash {
        hash = builtins.hashFile "sha256" tarball;
        hashAlgo = "sha256";
        toHashFormat = "sri";
      };
      storePath = toString (
        pkgs.requireFile {
          name = "frob-1.0.tar.gz";
          inherit hash;
          message = "";
          meta.license = pkgs.lib.licenses.free;
        }
      );
      expression = ''
        { lib, stdenvNoCC, requireFile }:
        stdenvNoCC.mkDerivation {
          pname = "frob";
          version = "1.0";
          src = requireFile {
            name = "frob-1.0.tar.gz";
            hash = "${hash}";
            message = "Added to the store by tulsi-adopt.";
            # requireFile assumes unfree; this file is free software.
            meta.license = lib.licenses.free;
          };
          installPhase = '''
            runHook preInstall
            install -Dm755 frob $out/bin/frob
            runHook postInstall
          ''';
          meta.description = "Frobnicates things";
          meta.mainProgram = "frob";
        }
      '';
      script = [
        {
          text = "Nothing in the Software Center fits, so I will package it.";
          tool_calls = [
            {
              name = "fetch_source";
              input.store_path = builtins.unsafeDiscardStringContext storePath;
            }
          ];
        }
        {
          text = "It is a tarball with a shell script.";
          tool_calls = [
            {
              name = "build_package";
              input = {
                name = "frob";
                inherit expression;
              };
            }
          ];
        }
        {
          text = "Built; let me try it.";
          tool_calls = [
            {
              name = "try_package";
              input.name = "frob";
            }
          ];
        }
        {
          text = "It works. Asking you to install it.";
          tool_calls = [
            {
              name = "propose_local_package";
              input = {
                name = "frob";
                inherit expression;
                version = "1.0";
                description = "Frobnicates things";
                origin = "frob-1.0.tar.gz";
                reason = "You asked to install frob-1.0.tar.gz.";
              };
            }
          ];
        }
        { text = "frob is installed and listed in the Software Center as made on this computer."; }
      ];
      # A program built for other distributions: the standard x86-64 loader path.
      foreign = pkgs.runCommand "foreign-hello" { nativeBuildInputs = [ pkgs.patchelf ]; } ''
        cp ${pkgs.hello}/bin/hello $out
        chmod u+w $out
        patchelf --set-interpreter /lib64/ld-linux-x86-64.so.2 --remove-rpath $out
      '';
    in
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/x11.nix")
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      test-support.displayManager.auto.user = "alice";
      users.users.alice.extraGroups = [ "wheel" ];
      virtualisation.memorySize = 4096;
      virtualisation.diskSize = 4096;

      tulsi.state = {
        enable = true;
        file = ./state-test.json;
      };
      tulsi.daemon = {
        enable = true;
        wheelNoPassword = true;
        packageIndex = ./index-test.json;
        rebuildCommand = [ "${pkgs.coreutils}/bin/true" ];
      };
      ocimum.softwareCenter.enable = true;
      ocimum.assistant.enable = true;
      tulsi.adopt.enable = true;
      services.starah = {
        enable = true;
        session.enable = false;
      };
      security.polkit.extraConfig = ''
        polkit.addRule(function(action, subject) {
          if (action.id.indexOf("org.starah.") == 0 && subject.isInGroup("wheel")) {
            return polkit.Result.YES;
          }
        });
      '';
      # Offline VM: what building the local package needs.
      system.extraDependencies = [ pkgs.stdenvNoCC ];
      nix.settings.substituters = pkgs.lib.mkForce [ ];

      environment.systemPackages = [
        pkgs.git
        pkgs.jq
        pkgs.xdotool
        pkgs.glib.bin
        pkgs.xdg-utils
      ];
      environment.etc."adopt/frob-1.0.tar.gz".source = tarball;
      environment.etc."adopt/foreign-hello".source = foreign;
      environment.etc."assistant/script.json".text = builtins.toJSON script;
    };

  testScript = ''
    import json
    from datetime import timedelta

    machine.wait_for_x()
    machine.wait_for_unit("tulsid.service")
    machine.wait_for_unit("starahd.service")
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

    def logs():
        machine.execute("tail -n 50 /tmp/assistant.log /tmp/adopt.log >&2")

    def window(title, timeout=60):
        try:
            machine.wait_until_succeeds(
                alice("xwininfo -root -tree 2>/dev/null") + f" | grep -qF -- '\"{title}\"'",
                timeout=timedelta(seconds=timeout),
            )
        except Exception:
            logs()
            raise

    def close_adopt():
        machine.execute("pkill -f tulsi-adopt")
        machine.wait_until_fails(alice("xwininfo -root -tree 2>/dev/null") + " | grep -qF 'Install the TulsiOS Way'")

    with subtest("apt explains the TulsiOS way and offers the Software Center package"):
        rc, out = machine.execute(alice("apt install -y hello 2>&1"), timeout=60)
        assert rc == 1, (rc, out)
        assert "does not install software with apt" in out and "tulsi install hello" in out, out
        window("Install the TulsiOS Way")
        # The window was started by the shim, and still knows it was apt.
        machine.wait_until_succeeds("pgrep -u alice -f -- '--tool apt --command apt install -y hello'", timeout=30)
        machine.sleep(3)
        machine.screenshot("adopt-apt")
        close_adopt()

    with subtest("a program built for another distribution opens tulsi-adopt"):
        machine.succeed("install -m755 /etc/adopt/foreign-hello /home/alice/foreign-hello")
        # Captured output: the popup must not keep the pipe open (timeout catches a hang).
        rc, out = machine.execute(alice("/home/alice/foreign-hello 2>&1"), timeout=60)
        assert rc == 127, (rc, out)
        assert "Could not start dynamically linked executable" in out, out
        window("Install the TulsiOS Way")
        machine.sleep(2)
        machine.screenshot("adopt-binary")
        close_adopt()

    with subtest("downloaded packages and archives open with tulsi-adopt"):
        for mime in ["application/vnd.debian.binary-package", "application/x-compressed-tar",
                     "application/vnd.appimage"]:
            out = machine.succeed(alice(f"xdg-mime query default {mime}")).strip()
            assert out == "tulsi-adopt.desktop", (mime, out)

    with subtest("the Assistant packages a tarball nobody packaged; a person approves it"):
        machine.succeed(alice(
            "OCIMUM_ASSISTANT_PROVIDER=fake:/etc/assistant/script.json "
            "OCIMUM_ASSISTANT_FAKE_LOG=/tmp/fake-model.jsonl "
            "OCIMUM_ASSISTANT_MCP=\"starah run --agent assistant -- tulsi-mcp --approval starah\" "
            "ocimum-assistant >/tmp/assistant.log 2>&1 &"
        ))
        window("Assistant", timeout=120)
        machine.succeed("install -D -o alice -m644 /etc/adopt/frob-1.0.tar.gz /home/alice/Downloads/frob-1.0.tar.gz")
        machine.succeed(alice("tulsi-adopt --file /home/alice/Downloads/frob-1.0.tar.gz >/tmp/adopt.log 2>&1 &"))
        window("Install the TulsiOS Way")
        machine.sleep(3)
        machine.screenshot("adopt-file")
        # Click "Ask the Assistant to Package It" (bottom right); a click needs no keyboard
        # focus, which the window manager may refuse xdotool (as in starah-setup.nix).
        machine.succeed(alice(
            "id=$(xdotool search --sync --name \"^Install the TulsiOS Way$\" | head -1); "
            "eval $(xdotool getwindowgeometry --shell $id); "
            "xdotool mousemove --window $id $((WIDTH - 140)) $((HEIGHT - 38)) click 1"
        ))
        try:
            machine.wait_until_succeeds("grep -q 'asking the Assistant' /tmp/adopt.log", timeout=timedelta(seconds=60))
        except Exception:
            machine.screenshot("adopt-ask-failed")
            logs()
            raise
        # The agent fetches, builds (in Nix's sandbox, as starah-assistant) and tries it,
        # then asks; nothing is installed before a person approves.
        try:
            machine.wait_until_succeeds("starah requests | grep -q frob", timeout=timedelta(minutes=10))
        except Exception:
            logs()
            machine.execute("cat /tmp/fake-model.jsonl >&2")
            raise
        machine.fail("grep -q frob /etc/nixos/tulsi/state.json")
        machine.succeed("ls /var/lib/starah-agents/assistant/packaging/frob/package.nix")
        machine.screenshot("adopt-request")
        req = machine.succeed("starah requests | grep frob | cut -f1").strip()
        machine.succeed(alice(f"starah approve {req}"))
        machine.wait_until_succeeds(
            "jq -e '.localPackages == [\"frob\"] and (.packages | index(\"frob\"))' /etc/nixos/tulsi/state.json",
            timeout=timedelta(minutes=2),
        )
        machine.succeed("grep -q 'stdenvNoCC.mkDerivation' /etc/nixos/tulsi/pkgs/frob/package.nix")
        meta = json.loads(machine.succeed("cat /etc/nixos/tulsi/pkgs/frob/meta.json"))
        assert meta["origin"] == "frob-1.0.tar.gz" and meta["version"] == "1.0", meta
        machine.wait_until_succeeds("git -C /etc/nixos log -1 --format=%s | grep -qx 'tulsi: add local package frob'")
        out = machine.succeed(alice("tulsi search frob"))
        assert "frob" in out, out

    with subtest("the model saw the real tool results"):
        requests = [json.loads(l) for l in machine.succeed("cat /tmp/fake-model.jsonl").splitlines()]
        def result(i):
            return requests[i]["messages"][-1]["content"][0]["content"]
        assert "compressed tar archive" in result(1), result(1)
        assert "Programs in bin/: frob" in result(2), result(2)
        assert "frob 1.0" in result(3), result(3)

    with subtest("undo removes the local package again"):
        machine.succeed(alice("tulsi undo"))
        machine.wait_until_succeeds("! test -e /etc/nixos/tulsi/pkgs/frob/package.nix", timeout=timedelta(minutes=1))
        machine.succeed("jq -e '(.localPackages // []) == []' /etc/nixos/tulsi/state.json")

    machine.succeed("cat /tmp/assistant.log /tmp/adopt.log >&2")
  '';
}
