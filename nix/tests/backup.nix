# tulsi.backup (ADR 0039): the Backup app and CLIs mirror home to a drive
# with a manifest, list backups, and merge one back without deleting.
{ self }:
{
  name = "backup";

  nodes.machine =
    { modulesPath, pkgs, ... }:
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      tulsi.backup.enable = true;
      users.users.alice.extraGroups = [ "wheel" ];
      security.sudo.wheelNeedsPassword = false;
      environment.systemPackages = [ pkgs.rsync ];
    };

  testScript = ''
    machine.wait_for_unit("multi-user.target")

    with subtest("Backup is installed, with a menu entry and rsync behind it"):
        machine.succeed("command -v tulsi-backup")
        machine.succeed("command -v tulsi-backup-app")
        machine.succeed("command -v rsync")
        machine.succeed("test -f /run/current-system/sw/share/applications/org.tulsi.Backup.desktop")

    with subtest("backing up writes a timestamped backup with a manifest"):
        machine.succeed("su - alice -c 'mkdir -p ~/Documents && echo hello > ~/Documents/note.txt'")
        out = machine.succeed("su - alice -c 'tulsi-backup backup /tmp/usb'")
        print(out)
        dest = out.strip().splitlines()[-1]
        machine.succeed(f"test -f {dest}/manifest.json")
        machine.succeed(f"grep -q hello {dest}/home/Documents/note.txt")

    with subtest("backups are listed, newest first"):
        machine.succeed("sleep 2")
        machine.succeed("su - alice -c 'echo second > /home/alice/Documents/second.txt'")
        machine.succeed("su - alice -c 'tulsi-backup backup /tmp/usb'")
        out = machine.succeed("su - alice -c 'tulsi-backup list /tmp/usb'")
        print(out)
        assert len(out.strip().splitlines()) == 2, out

    with subtest("restoring merges back without deleting"):
        machine.succeed("rm /home/alice/Documents/note.txt")
        machine.succeed("echo new > /home/alice/Documents/local.txt")
        newest = machine.succeed("su - alice -c 'tulsi-backup list /tmp/usb' | head -1 | cut -d' ' -f1").strip()
        machine.succeed(f"su - alice -c 'tulsi-backup restore {newest}'")
        machine.succeed("grep -q hello /home/alice/Documents/note.txt")
        machine.succeed("grep -q new /home/alice/Documents/local.txt")
  '';
}
