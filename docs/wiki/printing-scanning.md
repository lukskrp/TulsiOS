# Printers and scanners

Printers and scanners mostly just work, like on Mint. USB and network devices
are found automatically; no driver download needed.

- **Printers:** plug in or turn on a network printer, then open **Printers**
  (System Settings on Ocimum, System Settings on SonicDE). Driverless printers
  (IPP Everywhere/AirPrint/WSD) need nothing; common Brother, Canon, HP and
  Epson drivers are already installed.
- **Scanners:** open **Document Scanner** (Ocimum/dwm: Simple Scan; SonicDE:
  Skanlite). Network scanners appear via AirScan; USB scanners via SANE.
- **Non-free firmware is pre-installed** (Canon, Samsung, HP plugin data), so
  those printers work offline. To harden again, set
  `nixpkgs.config.allowUnfree = lib.mkForce false;` with `tulsi config` and add
  only the drivers you want via `allowUnfreePredicate`.
- Users are in the `lp` and `scanner` groups, so USB scanners and printer admin
  work without extra setup. Firewall opens mDNS (5353/UDP) for discovery;
  CUPS itself stays localhost-only.
