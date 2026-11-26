# Printers and scanners

Printers and scanners mostly just work, like on Mint. USB and network devices
are found automatically; no driver download needed.

- **Printers:** plug in or turn on a network printer, then open **Printers**
  (System Settings on Ocimum, System Settings on SonicDE). Driverless printers
  (IPP Everywhere/AirPrint/WSD) need nothing; common Brother, Canon, HP and
  Epson drivers are already installed.
- **Scanners:** open **Document Scanner** (Ocimum/dwm: Simple Scan; SonicDE:
  Skanlite). Network scanners appear via AirScan; USB scanners via SANE.
- **Some printers need the manufacturer's own driver** (many Canon PIXMA and
  MAXIFY, older Samsung, a few HP models). These drivers aren't free software, so
  they aren't installed by default: open **Drivers** and turn on **Printer
  drivers from Canon, Samsung and HP**. In a terminal, `tulsi config` with:
  `tulsi.printingScanning.unfreeDrivers = true;` and
  `nixpkgs.config.allowUnfree = true;`.
- Users are in the `lp` and `scanner` groups, so USB scanners and printer admin
  work without extra setup. Firewall opens mDNS (5353/UDP) for discovery;
  CUPS itself stays localhost-only.
