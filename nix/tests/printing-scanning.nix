# tulsi.printingScanning — Mint parity for printers and scanners.
# CUPS with common drivers (incl. pre-accepted non-free), driverless discovery
# (Avahi/mDNS, cups-browsed, ipp-usb), SANE + AirScan, simple-scan on
# Ocimum/dwm and skanlite on SonicDE.
{ self }:
{
  name = "printing-scanning";

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
                                   "nix-store -qR /run/current-system | grep -E -- '-gutenprint-|-hplip-|-splix-|-brlaser-|-cnijfilter2-'")
            for want in ["gutenprint", "hplip", "splix", "brlaser", "cnijfilter2"]:
                assert want in drivers, (want, drivers)

    with subtest("driverless USB and network discovery are on"):
        for node in [ocimum, sonic]:
            node.succeed("systemctl is-active ipp-usb.service")
            node.succeed("systemctl is-active avahi-daemon.service")
            node.succeed("getent hosts harmony 2>/dev/null; grep -q '^hosts:.*mdns' /etc/nsswitch.conf")
            ports = node.succeed("{ iptables-save 2>/dev/null || true; nft list ruleset 2>/dev/null || true; }")
            assert "5353" in ports, ports

    with subtest("SANE runs with the AirScan backend for driverless scanners"):
        for node in [ocimum, sonic]:
            node.succeed("test -f /etc/sane.d/airscan.conf")
            node.succeed("scanimage -V")
            node.succeed("ls /etc/udev/rules.d/*sane* /run/current-system/etc/udev/rules.d/*sane* 2>/dev/null || "
                         "nix-store -qR /run/current-system | grep -q sane-backends")

    with subtest("non-free printer firmware is pre-accepted (Mint parity)"):
        for node in [ocimum, sonic]:
            node.succeed("nix-store -qR /run/current-system | grep -q cnijfilter2")

    with subtest("Ocimum gets Document Scanner and Printers setup"):
        ocimum.succeed("command -v simple-scan")
        ocimum.succeed("command -v system-config-printer")
        ocimum.succeed("test -n \"$(ls /run/current-system/sw/share/applications | grep -i -e simple-scan -e system-config-printer)\"")

    with subtest("SonicDE gets Skanlite"):
        sonic.succeed("command -v skanlite || command -v skanlite-wrapped")
        sonic.succeed("test -n \"$(ls /run/current-system/sw/share/applications | grep -i skan)\"")
  '';
}
