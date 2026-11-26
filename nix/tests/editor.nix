# ADR 0031: Fresh is the editor in terminals. EDITOR and VISUAL are fresh for
# everyone (git, sudoedit and crontab -e follow them), nano is gone, Fresh has
# an app-menu entry, and double-clicked text files still open xed on Ocimum.
{ self }:
{
  name = "editor";

  nodes.machine =
    { modulesPath, pkgs, ... }:
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      users.users.alice.extraGroups = [ "wheel" ];
      security.sudo.wheelNeedsPassword = false;
      # A stand-in that records how it was started, in place of the real editor
      # (which needs a terminal); first on PATH, under Fresh's name.
      environment.etc."editor-test/fresh".source = pkgs.writeShellScript "fresh" ''
        echo "user=$(id -un) args=$*" >> /tmp/editor-test.log
      '';
      environment.systemPackages = [ pkgs.git ];
    };

  testScript = ''
    machine.wait_for_unit("multi-user.target")

    def alice(cmd):
        return machine.succeed(f"su - alice -c '{cmd}'")

    with subtest("Fresh is EDITOR and VISUAL; nano is gone"):
        assert alice("echo $EDITOR $VISUAL").split() == ["fresh", "fresh"]
        machine.succeed("command -v fresh")
        machine.fail("command -v nano")
        version = machine.succeed("fresh --version")
        assert "fresh" in version.lower(), version
        machine.succeed("test -f /run/current-system/sw/share/applications/fresh.desktop")

    with subtest("git and sudoedit open it, as the person"):
        stand_in = "PATH=/etc/editor-test:$PATH"
        alice(f"cd /tmp && git init -q repo && cd repo && {stand_in} git -c user.name=Alice -c user.email=alice@example.org commit -q --allow-empty 2>/dev/null; true")
        assert "COMMIT_EDITMSG" in machine.succeed("cat /tmp/editor-test.log"), machine.succeed("cat /tmp/editor-test.log")
        machine.succeed("rm /tmp/editor-test.log")
        # (NixOS's own /etc files are links into the store; a system file of the
        # person's, like the Starah rules, is a plain root-owned file.)
        machine.succeed("install -d -m755 /var/lib/editor-test && echo x > /var/lib/editor-test/target")
        status, out = machine.execute(
            f"su - alice -c '{stand_in} timeout 20 sudoedit /var/lib/editor-test/target' 2>&1")
        record = machine.succeed("cat /tmp/editor-test.log 2>/dev/null || true")
        # sudoedit runs the editor as alice, on a copy.
        assert status == 0 and "user=alice" in record, (status, out, record)
        assert "/var/lib/editor-test/target" not in record.split("args=")[1], record
  '';
}
