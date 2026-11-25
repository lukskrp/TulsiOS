# "Install it the TulsiOS way" (ADR 0013): apt and foreign binaries lead to
# tulsi-adopt; a downloaded tarball nobody packaged becomes a local package written
# by the Assistant (a scripted model here), built in Nix's sandbox by the Starah agent,
# approved by a person, added through tulsid, and undoable.
# Finding the package first (ADR 0018): other systems' names, the programs inside a
# download, language installers, store links for extensions.
{ self }:
let
  # A program built for another distribution: the standard loader path, no RUNPATH.
  foreignize =
    pkgs: program: name:
    pkgs.runCommand name { nativeBuildInputs = [ pkgs.patchelf ]; } ''
      cp ${program} $out
      chmod u+w $out
      patchelf --set-interpreter /lib64/ld-linux-x86-64.so.2 --remove-rpath $out
    '';
  # Recipes (ADR 0018): a prebuilt program that needs zlib, with an icon.
  squeezerTarball =
    pkgs:
    pkgs.runCommand "squeezer-2.8-linux-x86_64.tar.gz" { } ''
      mkdir squeezer-2.8
      cp ${foreignize pkgs "${pkgs.pigz}/bin/pigz" "squeezer"} squeezer-2.8/squeezer
      chmod 755 squeezer-2.8/squeezer
      cp ${pkgs.nixos-icons}/share/icons/hicolor/48x48/apps/nix-snowflake.png squeezer-2.8/icon.png
      tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -czf $out squeezer-2.8
    '';
  # A .deb with a menu entry that points into /usr.
  greeterDeb =
    pkgs:
    pkgs.runCommand "greeter_1.0_amd64.deb" { nativeBuildInputs = [ pkgs.dpkg ]; } ''
      mkdir -p pkg/DEBIAN pkg/usr/bin pkg/usr/share/applications
      printf '%s\n' 'Package: greeter' 'Version: 1.0' 'Architecture: amd64' \
        'Maintainer: Test <test@example.org>' 'Description: Greets people' > pkg/DEBIAN/control
      cp ${foreignize pkgs "${pkgs.hello}/bin/hello" "greeter"} pkg/usr/bin/greeter
      chmod 755 pkg/usr/bin/greeter
      printf '%s\n' '[Desktop Entry]' 'Type=Application' 'Name=Greeter' 'Exec=/usr/bin/greeter' \
        > pkg/usr/share/applications/greeter.desktop
      dpkg-deb --root-owner-group -b pkg $out
    '';
  # Source code that needs a library no table knows.
  needsFrobnicator =
    pkgs:
    pkgs.runCommand "needsfoo-1.0.tar.gz" { } ''
      mkdir needsfoo-1.0
      printf '%s\n' 'cmake_minimum_required(VERSION 3.10)' 'project(needsfoo C)' \
        'find_package(Frobnicator REQUIRED)' > needsfoo-1.0/CMakeLists.txt
      tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -czf $out needsfoo-1.0
    '';
  # A .deb whose file name says nothing; its control file and contents do.
  debFile =
    pkgs:
    pkgs.runCommand "download.deb" { nativeBuildInputs = [ pkgs.dpkg ]; } ''
      mkdir -p pkg/DEBIAN pkg/usr/bin
      printf '%s\n' 'Package: frobnicator-nightly' 'Version: 2.0' 'Architecture: amd64' \
        'Maintainer: Test <test@example.org>' 'Description: Says hi' > pkg/DEBIAN/control
      printf '#!/bin/sh\necho hi\n' > pkg/usr/bin/hi-there
      chmod 755 pkg/usr/bin/hi-there
      dpkg-deb --root-owner-group -b pkg $out
    '';
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
      virtualisation.diskSize = 8192;

      tulsi.state = {
        enable = true;
        file = ./state-test.json;
      };
      tulsi.daemon = {
        enable = true;
        wheelNoPassword = true;
        # The shared test index, plus a Python package for other systems' names.
        packageIndex = pkgs.writeText "adopt-index.json" (
          builtins.toJSON (
            builtins.fromJSON (builtins.readFile ./index-test.json)
            ++ [
              [
                "python3Packages.requests"
                "requests"
                "2.32.3"
                "HTTP library for Python"
                false
              ]
            ]
          )
        );
        # `hi-there` (inside the .deb) comes from hello; `nothing` from no indexed package.
        programIndex = pkgs.writeText "program-index-test.tsv" "hi-there\thello\nnothing\tnot-in-the-index\n";
        rebuildCommand = [ "${pkgs.coreutils}/bin/true" ];
      };
      ocimum.softwareCenter.enable = true;
      ocimum.assistant.enable = true;
      tulsi.adopt.enable = true;
      # ADR 0019: a failed recipe's draft is finished by hand in the Nix Editor.
      ocimum.nixEditor.enable = true;
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
      # Offline VM: what building the local packages needs (the Assistant's, and the
      # recipes': prebuilt programs, a .deb, and source built with autotools and CMake).
      system.extraDependencies = with pkgs; [
        stdenvNoCC
        stdenv
        autoPatchelfHook
        makeWrapper
        copyDesktopItems
        desktop-file-utils
        dpkg
        libarchive
        zlib
        zlib.dev
        pkg-config
        cmake
        hello.src
      ];
      nix.settings.substituters = pkgs.lib.mkForce [ ];

      environment.systemPackages = [
        pkgs.git
        pkgs.jq
        pkgs.xdotool
        pkgs.glib.bin
        pkgs.xdg-utils
      ];
      environment.etc."adopt/frob-1.0.tar.gz".source = tarball;
      environment.etc."adopt/download.deb".source = debFile pkgs;
      environment.etc."adopt/squeezer-2.8-linux-x86_64.tar.gz".source = squeezerTarball pkgs;
      environment.etc."adopt/greeter_1.0_amd64.deb".source = greeterDeb pkgs;
      environment.etc."adopt/needsfoo-1.0.tar.gz".source = needsFrobnicator pkgs;
      environment.etc."adopt/hello-2.12.tar.gz".source = pkgs.hello.src;
      # The Software Center's "Install from a File or Link" action, as its button runs it.
      environment.etc."adopt/sc-install-file" = {
        mode = "0755";
        text = ''
          #!/bin/sh
          exec gdbus call --session --dest org.tulsi.SoftwareCenter \
            --object-path /org/tulsi/SoftwareCenter --method org.gtk.Actions.Activate \
            install-file "[<'$1'>]" "{}"
        '';
      };
      environment.etc."adopt/foreign-hello".source = foreign;
      # What a person adds to needsfoo's draft after reading the guide: it needs no
      # Frobnicator if it is not built with CMake (installed before the draft's meta).
      environment.etc."adopt/needsfoo-fix.nix".text = ''
        dontConfigure = true;
        dontBuild = true;
        installPhase = '''
          runHook preInstall
          mkdir -p $out/bin
          echo "#!''${stdenv.shell}" > $out/bin/needsfoo
          echo "echo needsfoo works" >> $out/bin/needsfoo
          chmod +x $out/bin/needsfoo
          runHook postInstall
        ''';
      '';
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

    def terminal(cmd):
        """Runs `cmd` as alice outside the graphical session (no window opens)."""
        return machine.execute(f"su - alice -c 'unset DISPLAY WAYLAND_DISPLAY; {cmd} 2>&1'", timeout=60)

    with subtest("in a terminal, other systems' names lead to TulsiOS packages and services"):
        rc, out = terminal("apt install python3-requests openssh-server")
        assert rc == 1, (rc, out)
        assert "tulsi install python3Packages.requests" in out, out
        assert "tulsi service enable openssh" in out, out
        rc, out = terminal("pip install requests")
        assert rc == 1 and "tulsi install python3Packages.requests" in out, (rc, out)
        out = machine.succeed(alice("tulsi match --tool apt python3-requests"))
        assert "python3Packages.requests" in out and "Python package" in out, out

    with subtest("pip passes everything but installing on to the real pip"):
        machine.succeed("mkdir -p /tmp/fakebin && printf '#!/bin/sh\\necho \"real pip $*\"\\n' > /tmp/fakebin/pip && chmod 755 /tmp/fakebin/pip")
        rc, out = terminal("PATH=$PATH:/tmp/fakebin pip list")
        assert rc == 0 and "real pip list" in out, (rc, out)
        rc, out = terminal("PATH=$PATH:/tmp/fakebin pip install requests")
        assert rc == 1 and "real pip" not in out, (rc, out)

    with subtest("a .deb is recognised by what it contains, not its file name"):
        machine.succeed("install -D -o alice -m644 /etc/adopt/download.deb /home/alice/Downloads/download.deb")
        found = json.loads(machine.succeed(alice("tulsi inspect /home/alice/Downloads/download.deb")))
        assert found["kind"] == "deb" and found["name"] == "frobnicator-nightly", found
        assert found["version"] == "2.0" and found["programs"] == ["hi-there"], found
        machine.succeed(alice("tulsi-adopt --file /home/alice/Downloads/download.deb >/tmp/adopt-deb.log 2>&1 &"))
        window("Install the TulsiOS Way")
        machine.wait_until_succeeds("grep -q 'matches: hello (provides the program .hi-there.' /tmp/adopt-deb.log", timeout=60)
        machine.sleep(2)
        machine.screenshot("adopt-deb")
        close_adopt()

    with subtest("a Chrome Web Store link adds the extension, with confirmation and undo"):
        # Not one state-test.json already has (that would be "Nothing to change").
        ext = "aapbdbdomjkkjkaonfhkkikfgjllcleb"
        machine.succeed(alice("ocimum-software-center >/tmp/sc.log 2>&1 &"))
        window("Software Center")
        machine.succeed(alice(f"tulsi-adopt --url https://chromewebstore.google.com/detail/google-translate/{ext} >/tmp/adopt-url.log 2>&1"))
        try:
            window("Confirm Changes")
        except Exception:
            machine.screenshot("adopt-extension-failed")
            machine.execute("cat /tmp/sc.log /tmp/adopt-url.log >&2")
            raise
        machine.sleep(1)
        machine.screenshot("adopt-extension-confirm")
        machine.send_key("ret")
        machine.wait_until_succeeds(f"jq -e '.browserExtensions.chromium | index(\"{ext}\")' /etc/nixos/tulsi/state.json", timeout=timedelta(seconds=60))
        machine.succeed(alice("tulsi undo"))
        machine.wait_until_succeeds(f"! jq -e '.browserExtensions.chromium | index(\"{ext}\")' /etc/nixos/tulsi/state.json", timeout=timedelta(seconds=60))
        machine.execute("pkill -f ocimum-software-center")

    def recipe_build(file, flags, name):
        """`tulsi recipe build` as alice; returns (exit code, result)."""
        machine.succeed(f"install -D -o alice -m644 /etc/adopt/{file} /home/alice/Downloads/{file}")
        rc, _ = machine.execute(alice(
            f"tulsi recipe build /home/alice/Downloads/{file} {flags} "
            f"> /tmp/{name}.json 2> /tmp/{name}.log"), timeout=1800)
        result = json.loads(machine.succeed(f"cat /tmp/{name}.json"))
        if not result["ok"]:
            machine.execute(f"tail -n 60 /tmp/{name}.log >&2")
        return rc, result

    with subtest("a recipe packages a prebuilt program, finding the library it needs"):
        machine.succeed("install -D -o alice -m644 /etc/adopt/squeezer-2.8-linux-x86_64.tar.gz /home/alice/Downloads/squeezer-2.8-linux-x86_64.tar.gz")
        plan = json.loads(machine.succeed(alice("tulsi recipe plan /home/alice/Downloads/squeezer-2.8-linux-x86_64.tar.gz")))
        assert (plan["recipe"], plan["name"], plan["version"], plan["program"]) == ("archive", "squeezer", "2.8", "squeezer"), plan
        assert plan["menu"] and plan["license"] == "", plan
        rc, result = recipe_build("squeezer-2.8-linux-x86_64.tar.gz", "--free", "squeezer")
        assert rc == 0 and result["ok"], result["error"]
        machine.succeed("grep -q 'libz.so.1 comes from zlib' /tmp/squeezer.log")
        # The downloaded program was tried in a sandbox, not as alice.
        machine.succeed("grep -q 'in a sandbox: no network, none of your files' /tmp/squeezer.log")
        assert result["programs"] == ["squeezer"] and result["tried"]["ok"], result
        assert "pigz" in result["tried"]["output"], result["tried"]
        machine.succeed(f"test -e {result['outPath']}/share/applications/squeezer.desktop")
        machine.succeed(f"test -e {result['outPath']}/share/icons/hicolor/256x256/apps/squeezer.png")
        # Installed like any other change: history, and Undo.
        machine.succeed(alice("tulsi recipe install /tmp/squeezer.json"))
        machine.succeed("jq -e '.localPackages | index(\"squeezer\")' /etc/nixos/tulsi/state.json")
        machine.succeed("grep -q 'Made by a TulsiOS recipe' /etc/nixos/tulsi/pkgs/squeezer/package.nix")
        meta = json.loads(machine.succeed("cat /etc/nixos/tulsi/pkgs/squeezer/meta.json"))
        assert meta["origin"] == "recipe:archive squeezer-2.8-linux-x86_64.tar.gz", meta
        # Its download is kept unless said otherwise; that is a choice, with Undo.
        kept = "jq -e '.keepSources | index(\"squeezer\")' /etc/nixos/tulsi/state.json"
        machine.succeed(kept)
        machine.succeed(alice("tulsi keep-source squeezer off"))
        machine.fail(kept)
        machine.succeed(alice("tulsi undo"))
        machine.succeed(kept)
        # Taking back the install itself (by its id) removes the package and its kept download.
        install = machine.succeed("git -C /etc/nixos log -1 --format=%H --grep='add local package squeezer'").strip()
        machine.succeed(alice(f"tulsi undo {install}"))
        machine.succeed("! jq -e '.localPackages | index(\"squeezer\")' /etc/nixos/tulsi/state.json")
        machine.fail(kept)

    with subtest("a recipe packages a .deb, its menu entry pointing into the package"):
        rc, result = recipe_build("greeter_1.0_amd64.deb", "--free", "greeter")
        assert rc == 0 and result["ok"], result["error"]
        assert result["programs"] == ["greeter"] and result["tried"]["ok"], result
        assert "GNU Hello" in result["tried"]["output"], result["tried"]
        desktop = machine.succeed(f"cat {result['outPath']}/share/applications/greeter.desktop")
        assert "Exec=greeter" in desktop and "/usr/bin" not in desktop, desktop

    with subtest("a recipe builds source code; a name TulsiOS uses already gets -download"):
        src = "hello-2.12.tar.gz"
        machine.succeed(f"install -D -o alice -m644 /etc/adopt/{src} /home/alice/Downloads/{src}")
        plan = json.loads(machine.succeed(alice(f"tulsi recipe plan /home/alice/Downloads/{src}")))
        assert (plan["recipe"], plan["name"]) == ("autotools", "hello-download"), plan
        rc, result = recipe_build(src, "--free", "hello-src")
        assert rc == 0 and result["ok"], result["error"]
        assert "hello" in result["programs"] and result["tried"]["ok"], result

    with subtest("a recipe that cannot finish says why, and keeps its draft for the Assistant"):
        rc, result = recipe_build("needsfoo-1.0.tar.gz", "--free", "needsfoo")
        assert rc != 0 and not result["ok"], result
        assert "Frobnicator" in result["error"], result["error"]
        assert result["draft"].endswith("/needsfoo/package.nix") and "cmake" in result["expression"], result

    with subtest("a failed recipe is finished by hand in the Nix Editor, then installed"):
        machine.succeed(
            "mkdir -p /home/alice/.config/tulsi && "
            "printf '%s' '{\"whenNoPackage\": \"recipe\"}' > /home/alice/.config/tulsi/packaging.json && "
            "chown -R alice /home/alice/.config/tulsi"
        )
        machine.succeed(alice("tulsi-adopt --file /home/alice/Downloads/needsfoo-1.0.tar.gz >/tmp/adopt-edit.log 2>&1 &"))

        def edit_log(pattern, timeout=120):
            try:
                machine.wait_until_succeeds(f"grep -qE -- {pattern!r} /tmp/adopt-edit.log", timeout=timeout)
            except Exception:
                machine.execute("tail -n 60 /tmp/adopt-edit.log >&2")
                machine.screenshot("edit-failed")
                raise

        edit_log("step: details")
        machine.sleep(1)
        machine.send_key("alt-f")   # Free software
        machine.send_key("alt-u")   # Build: it fails, Frobnicator is nowhere
        edit_log("recipe finished: ok=False", timeout=1800)
        edit_log("step: install")
        machine.sleep(1)
        machine.screenshot("edit-recipe-failed")
        machine.send_key("alt-e")   # Edit It Yourself
        edit_log("opened /home/alice/.local/share/tulsi/recipes/needsfoo/package.nix")
        # Its title is "package.nix — Nix Editor".
        machine.wait_until_succeeds(
            alice("xwininfo -root -tree 2>/dev/null") + " | grep -qF 'Nix Editor'",
            timeout=timedelta(seconds=60))
        edit_log("lsp: ready")
        machine.sleep(2)
        machine.screenshot("edit-draft")

        # The person's fix, saved from another program: the editor reloads it.
        draft = "/home/alice/.local/share/tulsi/recipes/needsfoo/package.nix"
        text = machine.succeed(f"cat {draft}")
        fix = "".join("  " + line + "\n" for line in machine.succeed("cat /etc/adopt/needsfoo-fix.nix").splitlines())
        assert "\n  meta = " in text, text
        fixed = text.replace("\n  meta = ", "\n" + fix + "  meta = ", 1)
        import base64
        machine.succeed(f"echo {base64.b64encode(fixed.encode()).decode()} | base64 -d > {draft}")
        edit_log("reloaded " + draft)

        machine.succeed(alice("xdotool search --name \"Nix Editor\" windowactivate --sync"))
        machine.send_key("alt-t")   # Build and Try
        edit_log("build finished: ok=True", timeout=1800)
        machine.sleep(1)
        machine.screenshot("edit-built")
        machine.send_key("alt-i")   # Install, through the Software Center's confirmation
        edit_log("installing needsfoo")
        window("Confirm Changes")
        machine.send_key("ret")
        machine.wait_until_succeeds("jq -e '.localPackages | index(\"needsfoo\")' /etc/nixos/tulsi/state.json", timeout=60)
        meta = json.loads(machine.succeed("cat /etc/nixos/tulsi/pkgs/needsfoo/meta.json"))
        assert meta["origin"] == "edited:cmake needsfoo-1.0.tar.gz", meta
        machine.succeed("grep -q 'needsfoo works' /etc/nixos/tulsi/pkgs/needsfoo/package.nix")
        install = machine.succeed("git -C /etc/nixos log -1 --format=%H --grep='add local package needsfoo'").strip()
        machine.succeed(alice(f"tulsi undo {install}"))
        machine.succeed("! jq -e '.localPackages | index(\"needsfoo\")' /etc/nixos/tulsi/state.json")
        # Gone, not just told to go: the next Software Center must own its D-Bus name.
        close_adopt()
        # (The brackets keep pkill and pgrep from matching the shell running them.)
        machine.execute("pkill -f '[o]cimum-nix-editor|[o]cimum-software-center'")
        machine.wait_until_fails("pgrep -f '[o]cimum-nix-editor|[o]cimum-software-center'", timeout=timedelta(seconds=30))
        machine.succeed("rm /home/alice/.config/tulsi/packaging.json")

    with subtest("with recipes as the default, the popup goes straight to the questions"):
        machine.succeed(
            "mkdir -p /home/alice/.config/tulsi && "
            "printf '%s' '{\"whenNoPackage\": \"recipe\"}' > /home/alice/.config/tulsi/packaging.json && "
            "chown -R alice /home/alice/.config/tulsi"
        )
        machine.succeed(alice("tulsi-adopt --file /home/alice/Downloads/squeezer-2.8-linux-x86_64.tar.gz >/tmp/adopt-recipe.log 2>&1 &"))
        # The wizard skips "How to package it" and opens the Details step.
        machine.wait_until_succeeds("grep -q 'step: details' /tmp/adopt-recipe.log", timeout=60)
        machine.sleep(2)
        machine.screenshot("adopt-recipe-questions")
        close_adopt()
        machine.succeed("rm /home/alice/.config/tulsi/packaging.json")

    with subtest("the wizard, step by step with the keyboard, from the Software Center to an install"):
        machine.succeed(alice("ocimum-software-center >/tmp/sc-wizard.log 2>&1 &"))
        window("Software Center")
        # The wizard runs from the Software Center, so its log is the Software Center's.
        machine.succeed(alice("/etc/adopt/sc-install-file /home/alice/Downloads/greeter_1.0_amd64.deb"))
        window("Install the TulsiOS Way")

        def step(name, timeout=60):
            try:
                machine.wait_until_succeeds(f"grep -q 'step: {name}' /tmp/sc-wizard.log", timeout=timeout)
            except Exception:
                machine.screenshot(f"wizard-failed-{name}")
                machine.execute("tail -n 40 /tmp/sc-wizard.log >&2")
                raise
            machine.sleep(1)
            machine.screenshot(f"wizard-{name}")

        # Nothing in TulsiOS matches it, so the window stays on "What it is".
        step("about")
        machine.wait_until_succeeds("grep -q 'matches: $' /tmp/sc-wizard.log", timeout=60)
        machine.send_key("alt-n")
        step("match")
        machine.send_key("alt-n")
        step("how")
        machine.send_key("alt-n")
        step("details")
        machine.send_key("alt-f")   # Free software
        machine.send_key("alt-u")   # Build
        step("build")
        machine.wait_until_succeeds("grep -q 'recipe finished: ok=True' /tmp/sc-wizard.log", timeout=1800)
        step("install")
        machine.send_key("alt-i")   # Install: the Software Center's confirmation
        window("Confirm Changes")
        machine.send_key("ret")
        machine.wait_until_succeeds("jq -e '.localPackages | index(\"greeter\")' /etc/nixos/tulsi/state.json", timeout=60)
        machine.succeed("jq -e '.keepSources | index(\"greeter\")' /etc/nixos/tulsi/state.json")
        machine.succeed(alice("tulsi undo"))
        machine.execute("pkill -f ocimum-software-center")

    with subtest("with a match, the wizard opens on it"):
        rc, _ = machine.execute(alice("apt install -y hello >/dev/null 2>&1"))
        machine.wait_until_succeeds("pgrep -u alice -f -- '--tool apt'", timeout=30)
        window("Install the TulsiOS Way")
        machine.sleep(3)
        machine.screenshot("wizard-match-first")
        close_adopt()

    with subtest("the Assistant packages a tarball nobody packaged; a person approves it"):
        machine.succeed(alice(
            "OCIMUM_ASSISTANT_PROVIDER=fake:/etc/assistant/script.json "
            "OCIMUM_ASSISTANT_FAKE_LOG=/tmp/fake-model.jsonl "
            "OCIMUM_ASSISTANT_MCP=\"starah run --agent assistant -- tulsi-mcp --approval starah\" "
            "ocimum-assistant >/tmp/assistant.log 2>&1 &"
        ))
        window("Assistant", timeout=120)
        machine.succeed("install -D -o alice -m644 /etc/adopt/frob-1.0.tar.gz /home/alice/Downloads/frob-1.0.tar.gz")
        # The remembered choice is the Assistant, which has a model (a key): with nothing
        # matching, the popup hands the file over without asking again.
        machine.succeed(
            "mkdir -p /home/alice/.config/tulsi && "
            "printf '%s' '{\"whenNoPackage\": \"assistant\"}' > /home/alice/.config/tulsi/packaging.json && "
            "chown -R alice /home/alice/.config/tulsi"
        )
        machine.succeed(alice("ANTHROPIC_API_KEY=test tulsi-adopt --file /home/alice/Downloads/frob-1.0.tar.gz >/tmp/adopt.log 2>&1 &"))
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

    with subtest("without tulsid the shims say so, rather than that nothing matched"):
        machine.succeed("systemctl stop tulsid.service")
        rc, out = terminal("apt install hello")
        assert rc == 1 and "could not be asked" in out, (rc, out)

    machine.succeed("cat /tmp/assistant.log /tmp/adopt.log /tmp/adopt-deb.log >&2")
  '';
}
