# tulsi.printingScanning — Mint parity for printers and scanners.
# CUPS with the free common drivers, driverless discovery
# (Avahi/mDNS, cups-browsed, ipp-usb), SANE + AirScan, simple-scan on
# Ocimum/dwm and skanlite on SonicDE. The manufacturers' unfree drivers are
# opt-in (the SonicDE node turns them on).
{ self }:
{
  name = "printing-scanning";

  # The SonicDE node allows unfree software, as the Drivers app writes it
  # (checks.drivers-nvidia does the same); each node evaluates its own pkgs.
  node.pkgsReadOnly = false;

  nodes = {
    ocimum =
      { modulesPath, ... }:
      {
        imports = [
          self.nixosModules.default
          (modulesPath + "/../tests/common/user-account.nix")
        ];
        ocimum.desktop.enable = true;
        services.starah.session.enable = false;
      };
    sonic =
      { modulesPath, ... }:
      {
        imports = [
          self.nixosModules.default
          (modulesPath + "/../tests/common/user-account.nix")
        ];
        tulsi.desktop.session = "sonic";
        services.starah.session.enable = false;
        tulsi.printingScanning.unfreeDrivers = true;
        nixpkgs.config.allowUnfree = true;
      };
  };

  testScript = ''
    ocimum.wait_for_unit("multi-user.target")
    sonic.wait_for_unit("multi-user.target")

    with subtest("CUPS runs with the common drivers, browsed for network printers"):
        for node in [ocimum, sonic]:
            node.succeed("systemctl is-active cups.service")
            node.succeed("systemctl is-active cups-browsed.service")
            drivers = node.succeed("grep -o '/nix/store/[^ ]*' /etc/cups/cups-files.conf 2>/dev/null; "
                                   "nix-store -qR /run/current-system | grep -E -- '-gutenprint-|-hplip-|-splix-|-brlaser-'")
            for want in ["gutenprint", "hplip", "splix", "brlaser"]:
                assert want in drivers, (want, drivers)

    with subtest("driverless USB and network discovery are on"):
        for node in [ocimum, sonic]:
            # ipp-usb is on-demand (udev starts it when a USB printer appears),
            # so in a VM without one it is present but inactive.
            node.succeed("systemctl cat ipp-usb.service")
            node.succeed("command -v ipp-usb")
            node.succeed("systemctl is-active avahi-daemon.service")
            node.succeed("grep -q mdns /etc/nsswitch.conf")
            ports = node.succeed("{ iptables-save 2>/dev/null || true; nft list ruleset 2>/dev/null || true; }")
            assert "5353" in ports, ports

    with subtest("SANE runs with the AirScan backend for driverless scanners"):
        for node in [ocimum, sonic]:
            node.succeed("test -f /etc/sane-config/airscan.conf")
            node.succeed("scanimage -V")
            node.succeed("ls /etc/udev/rules.d/*sane* /run/current-system/etc/udev/rules.d/*sane* 2>/dev/null || "
                         "nix-store -qR /run/current-system | grep -q sane-backends")

    with subtest("the manufacturers' unfree drivers only when turned on"):
        ocimum.fail("nix-store -qR /run/current-system | grep -q -- '-cnijfilter2-'")
        sonic.succeed("nix-store -qR /run/current-system | grep -q -- '-cnijfilter2-'")
        sonic.succeed("nix-store -qR /run/current-system | grep -q -- '-samsung-unified-linux-driver-'")

    with subtest("Ocimum gets Document Scanner and Printers setup"):
        ocimum.succeed("command -v simple-scan")
        ocimum.succeed("command -v system-config-printer")
        ocimum.succeed("test -n \"$(ls /run/current-system/sw/share/applications | grep -i -e simple-scan -e system-config-printer)\"")

    with subtest("SonicDE gets Skanlite"):
        sonic.succeed("command -v skanlite || command -v skanlite-wrapped")
        sonic.succeed("test -n \"$(ls /run/current-system/sw/share/applications | grep -i skan)\"")
  '';
}
