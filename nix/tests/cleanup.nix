# ADR 0025: the weekly cleanup removes system generations older than 30 days,
# keeping the newest 10 and the booted one, and the disk settings that come with it.
{ self }:
{
  name = "cleanup";

  nodes.machine =
    { pkgs, lib, ... }:
    {
      imports = [ self.nixosModules.default ];
      tulsi.cleanup.enable = true;
      # Fifteen stand-in "generations": small distinct store paths.
      system.extraDependencies = map (i: pkgs.writeText "generation-${toString i}" (toString i)) (
        lib.range 1 15
      );
      environment.etc."cleanup-test/generations".text = lib.concatMapStringsSep "\n" (
        i: "${pkgs.writeText "generation-${toString i}" (toString i)}"
      ) (lib.range 1 15);
    };

  testScript = ''
    machine.wait_for_unit("multi-user.target")
    profile = "/nix/var/nix/profiles/system"
    booted = machine.succeed("readlink -f /run/booted-system").strip()

    def generations():
        out = machine.succeed(f"ls -d {profile}-*-link 2>/dev/null | sed -E 's/.*system-([0-9]+)-link/\\1/' | sort -n || true")
        return [int(g) for g in out.split()]

    # A test VM boots without a system profile; give the booted system its generation.
    if not generations():
        machine.succeed(f"nix-env -p {profile} --set {booted}")

    with subtest("the settings that come with it"):
        machine.succeed("grep -q 'SystemMaxUse=1G' /etc/systemd/journald.conf")
        machine.succeed("grep -qx 'auto-optimise-store = true' /etc/nix/nix.conf")
        machine.succeed("systemctl list-timers tulsi-cleanup.timer | grep -q tulsi-cleanup")

    with subtest("old generations go; the newest 10, young ones and the booted one stay"):
        before = generations()
        for path in machine.succeed("cat /etc/cleanup-test/generations").split():
            machine.succeed(f"nix-env -p {profile} --set {path}")
        made = [g for g in generations() if g not in before]
        assert len(made) == 15, made
        # The first 12 are 40 days old, the last 3 new.
        for g in made[:12] + before:
            machine.succeed(f"touch -h -d '40 days ago' {profile}-{g}-link")
        machine.succeed("systemctl start tulsi-cleanup.service")
        print(machine.succeed("journalctl -u tulsi-cleanup.service -o cat"))
        left = generations()
        assert left[-10:] == made[-10:], left
        # The booted system is kept although it is old and not among the newest.
        assert any(machine.succeed(f"readlink -f {profile}-{g}-link").strip() == booted for g in left), left
        assert len(left) == 11, left
        machine.succeed(f"test -e {booted}")
  '';
}
