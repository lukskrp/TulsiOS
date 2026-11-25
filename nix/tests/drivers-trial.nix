# ADR 0029: a driver change takes effect at the next restart, on trial. On
# systemd-boot the system before stays the default and the new one starts once:
# restarting without keeping it brings the old one back and the change is undone;
# kept, it stays. On GRUB, a change nobody keeps in time is undone.
#
# The rebuild is a stand-in that switches between two prebuilt systems ("old",
# and "new" with tulsi.drivers.games32Bit's marker), so no evaluation runs in the
# VM; the boot entries, the boot loader and tulsid's trial are real.
{ self }:
let
  machine =
    loader:
    {
      config,
      lib,
      pkgs,
      modulesPath,
      extendModules,
      ...
    }:
    let
      # The same machine with the driver change: what the rebuild builds when
      # configuration.nix has it.
      newSystem =
        (extendModules {
          modules = [
            {
              driversTest.isNew = true;
              environment.etc."drivers-test-variant".text = lib.mkForce "new";
            }
          ];
        }).config.system.build.toplevel;
      bootRebuild = pkgs.writeShellScript "boot-rebuild" ''
        set -eu
        if grep -q 'games32Bit = true' /etc/nixos/configuration.nix; then
          sys=${if config.driversTest.isNew then "/nonexistent" else newSystem}
        else
          sys=$(cat /var/lib/drivers-test/old)
        fi
        nix-env -p /nix/var/nix/profiles/system --set "$sys"
        "$sys/bin/switch-to-configuration" boot
      '';
    in
    {
      options.driversTest.isNew = lib.mkOption {
        type = lib.types.bool;
        default = false;
      };

      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/user-account.nix")
      ];

      config = lib.mkMerge [
        {
          environment.etc."drivers-test-variant".text = "old";
          system.extraDependencies = lib.mkIf (!config.driversTest.isNew) [ newSystem ];
          virtualisation.useBootLoader = true;
          virtualisation.memorySize = 1536;
          tulsi.drivers.app.enable = true;
          tulsi.state = {
            enable = true;
            file = ./state-test.json;
          };
          tulsi.daemon = {
            enable = true;
            rebuildCommand = [ "${pkgs.coreutils}/bin/true" ];
            bootRebuildCommand = [ "${bootRebuild}" ];
            trialTimeout = 20;
          };
          environment.systemPackages = [
            pkgs.git
            pkgs.efibootmgr
          ];
        }
        (lib.mkIf (loader == "systemd-boot") {
          virtualisation.useEFIBoot = true;
          boot.loader.systemd-boot.enable = true;
          boot.loader.efi.canTouchEfiVariables = true;
        })
        (lib.mkIf (loader == "grub") {
          boot.loader.grub.enable = true;
          boot.loader.grub.device = "/dev/vda";
          boot.loader.systemd-boot.enable = false;
        })
      ];
    };
in
{
  name = "drivers-trial";

  nodes.efi = machine "systemd-boot";
  nodes.bios = machine "grub";

  testScript = ''
    import json

    def boot(m):
        m.wait_for_unit("multi-user.target")
        m.wait_for_unit("tulsid.service")

    def variant(m):
        return m.succeed("cat /etc/drivers-test-variant").strip()

    def trial(m):
        return json.loads(m.succeed("tulsi trial status --json"))

    def configuration(m):
        # (Undoing the first edit removes the file it created.)
        return m.succeed("cat /etc/nixos/configuration.nix 2>/dev/null || true")

    def restart(m):
        m.shutdown()
        m.start()
        boot(m)

    def wait_state(m, state):
        m.wait_until_succeeds(
            f"tulsi trial status --json | grep -q '\"state\":\"{state}\"'", timeout=180)

    def prepare(m):
        boot(m)
        assert variant(m) == "old"
        # The stand-in rebuild returns to the system this machine started with.
        m.succeed("mkdir -p /var/lib/drivers-test && readlink -f /run/booted-system > /var/lib/drivers-test/old")
        # A test VM may start without a system profile: give it its generation.
        m.succeed("test -e /nix/var/nix/profiles/system || nix-env -p /nix/var/nix/profiles/system --set $(cat /var/lib/drivers-test/old)")

    def choose(m):
        out = m.succeed("tulsi-drivers set games32 2>&1")
        print(out)
        assert "takes effect when you restart" in out, out
        assert "games32Bit = true" in configuration(m)
        t = trial(m)
        assert t["state"] == "pending", t
        return t

    start_all()

    with subtest("systemd-boot: the new system starts once; not kept, it is undone"):
        prepare(efi)
        t = choose(efi)
        # The new system starts once; the one before stays the default. (NixOS
        # names boot entries by a hash; find each generation's by its init.)
        entries = json.loads(efi.succeed("bootctl list --json=short 2>/dev/null"))

        def entry_of(generation):
            system = efi.succeed(f"readlink -f /nix/var/nix/profiles/system-{generation}-link").strip()
            return next(e["id"] for e in entries if f"init={system}/init" in e.get("options", ""))

        efivar = "/sys/firmware/efi/efivars/LoaderEntry{}-4a67b082-0a4c-41cf-b6c7-440b29bb8c4f"
        efi.succeed(f"tr -d '\\0' < {efivar.format('OneShot')} | grep -qF '{entry_of(t['newGeneration'])}'")
        efi.succeed(f"tr -d '\\0' < {efivar.format('Default')} | grep -qF '{entry_of(t['oldGeneration'])}'")
        # Changing anything else waits for the trial.
        efi.succeed("cp /etc/nixos/configuration.nix /tmp/other.nix && echo '# other' >> /tmp/other.nix")
        status, out = efi.execute("tulsi config apply /tmp/other.nix --summary other 2>&1")
        print(out)
        assert status != 0 and "waits for a restart" in out, out
        restart(efi)
        assert variant(efi) == "new"
        wait_state(efi, "testing")
        # Restarting without keeping it: back to the system before, and undone.
        restart(efi)
        assert variant(efi) == "old"
        wait_state(efi, "reverted")
        assert "games32Bit" not in configuration(efi)
        commits = efi.succeed("git -C /etc/nixos log --format=%s -3")
        assert commits.splitlines()[0].startswith("tulsi: undo"), commits
        print(efi.succeed("tulsi trial status"))
        efi.succeed("tulsi trial dismiss")
        assert trial(efi)["state"] == "none"

    with subtest("systemd-boot: kept, it stays"):
        choose(efi)
        restart(efi)
        assert variant(efi) == "new"
        wait_state(efi, "testing")
        print(efi.succeed("tulsi-drivers keep"))
        assert trial(efi)["state"] == "none"
        restart(efi)
        assert variant(efi) == "new"
        assert "games32Bit = true" in configuration(efi)
        assert trial(efi)["state"] == "none"

    with subtest("GRUB: not kept in time, it is undone; the next start is the old one"):
        prepare(bios)
        choose(bios)
        restart(bios)
        assert variant(bios) == "new"
        wait_state(bios, "testing")
        # trialTimeout is 20 s here.
        wait_state(bios, "reverted")
        assert "games32Bit" not in configuration(bios)
        restart(bios)
        assert variant(bios) == "old"
  '';
}
