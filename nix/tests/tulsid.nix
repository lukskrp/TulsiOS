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

    # ADR 0017: the system flake follows a release branch; here a local git repo
    # stands in for github:lukskrp/TulsiOS/stable.
    nix = "nix --extra-experimental-features 'nix-command flakes'"
    commit = "git -c user.name=t -c user.email=t@t commit -q"
    machine.succeed(
        "mkdir -p /srv/tulsios",
        "git -C /srv/tulsios init -q -b stable",
        "echo 0.1.0 > /srv/tulsios/VERSION",
        "echo '{ outputs = _: { }; }' > /srv/tulsios/flake.nix",
        f"cd /srv/tulsios && git add -A && {commit} -m r1",
        "printf '%s\\n' '{' '  inputs.tulsi.url = \"git+file:///srv/tulsios?ref=stable\";' "
        "'  outputs = _: { };' '}' > /etc/nixos/flake.nix",
        f"cd /etc/nixos && {nix} flake lock path:/etc/nixos",
        f"cd /etc/nixos && git add flake.nix flake.lock && {commit} -m 'follow the release branch'",
    )
    r1 = machine.succeed("git -C /srv/tulsios rev-parse HEAD").strip()

    with subtest("upgrade --check: nothing newer yet"):
        out = machine.succeed(as_user("alice", "tulsi upgrade --check"))
        print(out)
        assert "TulsiOS 0.1.0" in out and "newest release" in out, out

    with subtest("a new release is reported, and tulsi upgrade moves to it"):
        machine.succeed(
            "echo 0.2.0 > /srv/tulsios/VERSION",
            f"cd /srv/tulsios && {commit} -am r2",
        )
        r2 = machine.succeed("git -C /srv/tulsios rev-parse HEAD").strip()
        out = machine.succeed(as_user("alice", "tulsi upgrade --check"))
        assert "TulsiOS 0.2.0 is available" in out, out
        out = machine.succeed(as_user("alice", "tulsi upgrade"))
        print(out)
        assert "upgrade TulsiOS 0.1.0" in out and "0.2.0" in out, out
        machine.succeed(f"grep -q {r2} /etc/nixos/flake.lock")
        machine.succeed("git -C /etc/nixos log -1 --format=%s | grep -q 'tulsi: upgrade TulsiOS 0.1.0'")
        machine.succeed("git -C /etc/nixos diff --quiet HEAD -- flake.lock")
        out = machine.succeed(as_user("alice", "tulsi upgrade --check"))
        assert "TulsiOS 0.2.0" in out and "newest release" in out, out

    with subtest("undo takes the upgrade back"):
        machine.succeed(as_user("alice", "tulsi undo"))
        machine.succeed(f"grep -q {r1} /etc/nixos/flake.lock")
        machine.fail(f"grep -q {r2} /etc/nixos/flake.lock")
        machine.succeed(as_user("alice", "tulsi history") + " | grep -q 'undo upgrade TulsiOS'")

    with subtest("only administrators upgrade"):
        out = machine.fail(as_user("bob", "tulsi upgrade 2>&1"))
        assert "NotAuthorized" in out, out
        machine.succeed(f"grep -q {r1} /etc/nixos/flake.lock")
  '';
}
