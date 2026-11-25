# ADR 0029: NVIDIA's driver as the Drivers app sets it (tulsi.drivers.nvidia):
# the kernel modules are built for TulsiOS's kernel, and XLibre, TulsiOS's X
# server, loads NVIDIA's X driver (whose ABI is Xorg's). The VM has no NVIDIA
# card, so the driver then finds no device; that it loads at all is the point.
# A real card is checked on real hardware (see the ADR).
{ self }:
{
  name = "drivers-nvidia";

  # The node allows unfree software, as the Drivers app does.
  node.pkgsReadOnly = false;

  nodes.machine =
    { lib, pkgs, ... }:
    {
      imports = [ self.nixosModules.default ];
      # Test VMs force the modesetting driver (mkVMOverride); the Drivers app's
      # choice has to win here as it does on a real machine.
      services.xserver.videoDrivers = lib.mkOverride 9 [ "nvidia" ];
      nixpkgs.config.allowUnfree = true;
      tulsi.drivers.app.enable = true;
      tulsi.drivers.nvidia = {
        enable = true;
        branch = "production";
        open = true;
      };
      services.xserver.enable = true;
      services.xserver.displayManager.lightdm.enable = true;
      virtualisation.memorySize = 1536;
    };

  testScript = ''
    import json

    machine.wait_for_unit("multi-user.target")

    with subtest("the open kernel modules are built for this kernel"):
        version = machine.succeed("modinfo -F version nvidia").strip()
        system = json.loads(machine.succeed("cat /etc/tulsi/drivers.json"))
        assert version == system["nvidia"]["production"]["version"], (version, system)
        assert "MIT" in machine.succeed("modinfo -F license nvidia"), "not the open modules"
        kernel = machine.succeed("uname -r").strip()
        assert kernel.startswith(system["kernel"].rsplit(".", 1)[0]), (kernel, system["kernel"])

    with subtest("XLibre loads NVIDIA's X driver"):
        # The display manager starts X at boot; with no NVIDIA card it then
        # finds no screen, after loading the driver. Its log says how far it got.
        machine.wait_until_succeeds("grep -q 'LoadModule: \"nvidia\"' /var/log/X.0.log", timeout=120)
        xlog = machine.succeed("cat /var/log/X.0.log")
        print(xlog)
        assert "XLibre" in xlog
        assert "nvidia_drv.so" in xlog, "NVIDIA's X driver was not found"
        assert 'Failed to load module "nvidia"' not in xlog, "XLibre refused NVIDIA's X driver"
        assert 'Module nvidia: vendor="NVIDIA Corporation"' in xlog
  '';
}
