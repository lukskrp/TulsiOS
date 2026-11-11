# tulsid end to end on the bus: polkit, D-Bus policy, git history, failure
# restore and undo. The rebuild command is a stand-in (tests have no network
# to build real systems); scripts/vm-e2e.sh covers real rebuilds.
{ self }:
{
  name = "tulsid";

  nodes.machine =
    { pkgs, ... }:
    {
      imports = [ self.nixosModules.default ];

      tulsi.state = {
        enable = true;
        file = ./state-test.json;
      };

      tulsi.daemon = {
        enable = true;
        wheelNoPassword = true;
        rebuildCommand = [
          "${pkgs.writeShellScript "fake-rebuild" ''
            echo "rebuilding from $PWD"
            if grep -q '"brokenpkg"' tulsi/state.json; then
              echo "error: tulsi.state: unknown package 'brokenpkg'" >&2
              exit 1
            fi
            echo ok >> /tmp/rebuilds
          ''}"
        ];
      };

      environment.systemPackages = [ pkgs.git ];
      users.users.alice = {
        isNormalUser = true;
        extraGroups = [ "wheel" ];
      };
      users.users.bob.isNormalUser = true;
    };

  testScript = ''
    state = "/etc/nixos/tulsi/state.json"

    def as_user(user, cmd):
        return f"su - {user} -c '{cmd}'"

    machine.wait_for_unit("tulsid.service")

    with subtest("state and git history are initialized"):
        machine.succeed(f"grep -q hello {state}")
        machine.succeed("git -C /etc/nixos log --format=%s | grep -qx 'tulsi: initial state'")

    with subtest("an administrator can install a package"):
        out = machine.succeed(as_user("alice", "tulsi install cowsay"))
        assert "rebuilding from /etc/nixos" in out, out
        machine.succeed(f"grep -q cowsay {state}")
        machine.succeed("git -C /etc/nixos log -1 --format=%s | grep -qx 'tulsi: install cowsay'")
        machine.succeed("test $(wc -l < /tmp/rebuilds) -eq 1")
        machine.succeed(as_user("alice", "tulsi status") + " | grep -q cowsay")

    with subtest("installing again is a no-op"):
        out = machine.succeed(as_user("alice", "tulsi install cowsay"))
        assert "Nothing to change" in out, out
        machine.succeed("test $(wc -l < /tmp/rebuilds) -eq 1")

    with subtest("a failed rebuild restores the previous state"):
        machine.fail(as_user("alice", "tulsi install brokenpkg"))
        machine.fail(f"grep -q brokenpkg {state}")
        machine.succeed("git -C /etc/nixos diff --quiet HEAD -- tulsi/state.json")

    with subtest("invalid input is rejected before anything runs"):
        machine.fail(as_user("alice", 'tulsi install "x;reboot"'))
        machine.fail(as_user("alice", "tulsi remove notinstalled"))
        machine.succeed("test $(wc -l < /tmp/rebuilds) -eq 1")

    with subtest("undo reverts the latest change"):
        machine.succeed(as_user("alice", "tulsi undo"))
        machine.fail(f"grep -q cowsay {state}")
        machine.succeed(as_user("alice", "tulsi history") + " | grep -q 'undo install cowsay'")

    with subtest("users who are not administrators are refused"):
        out = machine.fail(as_user("bob", "tulsi install sl 2>&1"))
        assert "NotAuthorized" in out, out
        machine.fail(f"grep -q '\"sl\"' {state}")
        # Reading is allowed for everyone.
        machine.succeed(as_user("bob", "tulsi status"))
  '';
}
