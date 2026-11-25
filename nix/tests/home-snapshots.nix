# ADR 0027: a history of the home folders. Snapshots of a btrfs /home bring back
# deleted and overwritten files (only to their owner), "free space" drops old
# ones, the Welcome window turns the history on with `tulsi config`, and the
# trash empties itself.
{ self }:
{
  name = "home-snapshots";

  nodes.machine =
    { modulesPath, pkgs, ... }:
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      users.users.alice.extraGroups = [ "wheel" ];
      virtualisation.emptyDiskImages = [ 2048 ];
      virtualisation.fileSystems."/home" = {
        device = "/dev/vdb";
        fsType = "btrfs";
        autoFormat = true;
      };
      boot.supportedFilesystems = [ "btrfs" ];

      tulsi.homeSnapshots.enable = true;
      tulsi.welcome.enable = true;
      tulsi.state = {
        enable = true;
        file = ./state-test.json;
      };
      tulsi.daemon = {
        enable = true;
        wheelNoPassword = true;
        rebuildCommand = [ "${pkgs.coreutils}/bin/true" ];
      };
      environment.systemPackages = [ pkgs.git ];
    };

  testScript = ''
    def alice(cmd):
        return f"su - alice -c '{cmd}'"

    machine.wait_for_unit("multi-user.target")
    machine.wait_for_unit("tulsi-home-snapshots-setup.service")
    machine.wait_for_unit("tulsid.service")
    # The btrfs /home disk is mounted after the accounts were made: give them homes.
    for user in ["alice", "bob"]:
        machine.succeed(f"install -d -m700 -o {user} -g users /home/{user}")

    def snap(description):
        machine.succeed(f"snapper -c home create -d {description}")

    with subtest("deleted and overwritten files come back, to their owner only"):
        machine.succeed(alice("echo first > ~/notes.txt && mkdir -p ~/project && echo code > ~/project/main.c"))
        snap("one")
        machine.succeed(alice("echo second > ~/notes.txt"))
        snap("two")
        machine.succeed(alice("rm -rf ~/notes.txt ~/project"))
        listed = machine.succeed(alice("tulsi-file-history list ~/notes.txt"))
        assert len(listed.strip().splitlines()) == 2, listed
        machine.succeed(alice("tulsi-file-history restore ~/notes.txt"))
        assert machine.succeed(alice("cat ~/notes.txt")).strip() == "second"
        first = listed.strip().splitlines()[-1].split()[0]
        machine.succeed(alice(f"tulsi-file-history restore ~/notes.txt --from {first} --copy"))
        assert machine.succeed(alice("cat ~/notes\\ \\(from*.txt")).strip() == "first"
        machine.succeed(alice("tulsi-file-history restore ~/project"))
        assert machine.succeed(alice("cat ~/project/main.c")).strip() == "code"
        # bob can look into the snapshots, but not at alice's files there.
        machine.succeed("su - bob -c 'ls /home/.snapshots'")
        machine.fail("su - bob -c 'cat /home/.snapshots/*/snapshot/alice/notes.txt'")

    with subtest("restoring over a file puts it in the trash first"):
        machine.succeed(alice("echo third > ~/notes.txt"))
        machine.succeed(alice("tulsi-file-history restore ~/notes.txt"))
        machine.succeed(alice("grep -rq third ~/.local/share/Trash/files/"))

    with subtest("free space now: only the newest snapshot stays"):
        out = machine.succeed(alice("tulsi-file-history free --keep 1"))
        assert "Deleted" in out, out
        assert len(machine.succeed(alice("tulsi-file-history snapshots")).strip().splitlines()) == 1

    with subtest("the TulsiOS Wiki is on the computer, warning about agents installed elsewhere"):
        wiki = "/run/current-system/sw/share/tulsios/wiki"
        for page in ["index", "ai-agents", "file-history", "disk-space"]:
            machine.succeed(f"test -s {wiki}/{page}.html")
        machine.succeed(f"grep -q 'Agents installed outside TulsiOS' {wiki}/ai-agents.html")
        machine.succeed(f"grep -q '<table>' {wiki}/ai-agents.html")
        machine.succeed("test -e /run/current-system/sw/share/applications/org.tulsi.Wiki.desktop")
        out = machine.fail("tulsi-wiki nosuchpage 2>&1")
        assert "ai-agents" in out, out

    with subtest("the trash empties itself after 30 days"):
        machine.succeed("test -e /etc/systemd/user/tulsi-trash-expire.timer")

    with subtest("Welcome: not in a virtual machine at first login; turns the history on"):
        machine.succeed(alice("timeout 20 tulsi-welcome --first-login"))
        machine.fail(alice("test -e ~/.local/state/tulsi/welcome-shown"))
        out = machine.succeed(alice("tulsi-welcome --turn-on-history"))
        machine.log(out)
        machine.succeed("grep -q 'tulsi.homeSnapshots.enable = true;' /etc/nixos/configuration.nix")
        machine.succeed("git -C /etc/nixos log -1 --format=%s | grep -q 'Keep a history of home folders'")
        machine.succeed(alice("tulsi undo"))
        machine.fail("grep -q 'tulsi.homeSnapshots.enable' /etc/nixos/configuration.nix")
  '';
}
