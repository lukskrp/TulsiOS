# Adoption of store-installed browser extensions: tulsi-extwatch runs as the
# logged-in user's service, sees new extensions in Firefox and Chromium
# profiles and makes them declarative through tulsid. alice is NOT an
# administrator: extension-only changes need no password, packages still do.
{ self }:
{
  name = "browser-extensions";

  nodes.machine =
    { pkgs, modulesPath, ... }:
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/x11.nix")
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      test-support.displayManager.auto.user = "alice";

      tulsi.state = {
        enable = true;
        file = ./state-test.json;
      };
      tulsi.daemon = {
        enable = true;
        packageIndex = ./index-test.json;
        rebuildCommand = [ "${pkgs.coreutils}/bin/true" ];
      };
      tulsi.browserExtensions.adopt.grace = 1;
      environment.systemPackages = [ pkgs.git ];

      environment.etc."test/firefox-extensions.json".text = builtins.toJSON {
        schemaVersion = 36;
        addons = [
          {
            id = "{446900e4-71c2-419f-a6a7-df9c091e268b}";
            type = "extension";
            location = "app-profile";
            sourceURI = "https://addons.mozilla.org/firefox/downloads/file/1/bitwarden.xpi";
            defaultLocale.name = "Bitwarden";
          }
          {
            id = "sideloaded@example.org";
            type = "extension";
            location = "app-profile";
            sourceURI = "file:///home/alice/sideloaded.xpi";
            defaultLocale.name = "Side-loaded";
          }
          {
            id = "keep@example.org";
            type = "extension";
            location = "app-profile";
            sourceURI = "https://addons.mozilla.org/firefox/downloads/file/3/keep.xpi";
            defaultLocale.name = "Kept imperative";
          }
        ];
      };
      environment.etc."test/chromium-prefs.json".text = builtins.toJSON {
        extensions.settings.nngceckbapebfimnlniiiahkandclblb = {
          location = 1;
          from_webstore = true;
          manifest.name = "Bitwarden Password Manager";
        };
      };
    };

  testScript = ''
    state = "/etc/nixos/tulsi/state.json"

    def alice(cmd):
        return f"su - alice -c 'XDG_RUNTIME_DIR=/run/user/1000 {cmd}'"

    machine.wait_for_x()
    machine.wait_for_unit("tulsid.service")

    with subtest("the watcher runs in alice's graphical session"):
        machine.wait_until_succeeds(alice("systemctl --user is-active tulsi-extwatch"))

    with subtest("a remembered 'keep it imperative' choice is respected"):
        machine.succeed(alice("mkdir -p ~/.local/state/tulsi"))
        machine.succeed(
            alice("echo {\\\"keep_imperative\\\":[\\\"firefox:keep@example.org\\\"]} > ~/.local/state/tulsi/extwatch.json")
        )

    with subtest("a Firefox store install becomes declarative"):
        machine.succeed(alice("mkdir -p ~/.mozilla/firefox/test.default"))
        machine.succeed(alice("cp /etc/test/firefox-extensions.json ~/.mozilla/firefox/test.default/extensions.json"))
        machine.wait_until_succeeds(f"grep -qF '{{446900e4-71c2-419f-a6a7-df9c091e268b}}' {state}")
        machine.wait_until_succeeds(
            "git -C /etc/nixos log --format=%s | grep -qF "
            "'tulsi: add firefox extension {446900e4-71c2-419f-a6a7-df9c091e268b}'"
        )

    with subtest("side-loaded and kept-imperative extensions are left alone"):
        machine.sleep(5)
        machine.fail(f"grep -q sideloaded@example.org {state}")
        machine.fail(f"grep -q keep@example.org {state}")

    with subtest("a Chrome Web Store install becomes declarative"):
        machine.succeed(alice("mkdir -p ~/.config/chromium/Default"))
        machine.succeed(
            "install -o alice -m 600 /etc/test/chromium-prefs.json "
            "'/home/alice/.config/chromium/Default/Secure Preferences'"
        )
        machine.wait_until_succeeds(f"grep -q nngceckbapebfimnlniiiahkandclblb {state}")

    with subtest("the watcher reported what it did"):
        journal = machine.succeed(alice("journalctl --user -u tulsi-extwatch --no-pager"))
        assert "adopted" in journal, journal

    with subtest("extension rights do not extend to packages"):
        out = machine.fail(alice("tulsi install sl 2>&1"))
        assert "NotAuthorized" in out, out
  '';
}
