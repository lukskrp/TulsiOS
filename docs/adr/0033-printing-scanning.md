# ADR 0033: Printers and scanners work like Mint

Status: accepted (2026-11-27).

## Context

TulsiOS printed but didn't scan, and printing needed setup Mint does by default.

- **CUPS was on** (`nix/hosts/desktop`), with the Cinnamon `printers` applet and
  Sonic's `print-manager`, but no drivers, no printer GUI on Ocimum, no SANE,
  no scanner app, no Avahi discovery. USB + network devices mostly needed manual setup.
- The person asked for Mint parity on Ocimum first, all desktops: a document
  scanner app and printer drivers shipped by default, even non-free — with
  TulsiOS's agentic focus, safety, replicability and curated stacks kept.

## Decision

**`tulsi.printingScanning`** (`nix/modules/printing-scanning.nix`): on with any
TulsiOS desktop (Ocimum, SonicDE, dwm), off on the live installer.

- **CUPS:** `services.printing` + `browsed` (network printers), drivers
  `gutenprint, gutenprintBin, hplip, splix, brlaser` (all free software).
- **Driverless:** `services.ipp-usb` (USB IPP/AirPrint/WSD as network devices)
  + `services.avahi` with `nssmdns4` and firewall open (mDNS discovery).
- **Scanning:** `hardware.sane` + `sane-airscan` backend, firewall open for
  network scanners.
- **Apps:** `simple-scan` + `system-config-printer` on Ocimum/dwm (Mint Cinnamon
  parity); `skanlite` + `system-config-printer` on SonicDE (`print-manager`
  stays as Sonic's frontend).
- **The manufacturers' unfree drivers are opt-in:**
  `tulsi.printingScanning.unfreeDrivers` adds `cnijfilter2` (Canon),
  `samsung-unified-linux-driver`, `hplipWithPlugin` and the foomatic non-free PPDs.
  It needs `nixpkgs.config.allowUnfree = true` (an assertion says so), and the
  Drivers app's "Printer drivers" choice writes both through `tulsi config`.
  Amended 2026-11-26: the first version set `allowUnfree = mkDefault true` for
  every desktop, which turned unfree software on system-wide against TulsiOS's
  free-by-default rule, and broke NixOS tests that share read-only pkgs.
- **Users:** installer `DEFAULT_GROUPS` + reference/VM users gain `lp, scanner`
  (USB scanner ACLs, CUPS admin).

## Consequences

- Printers/scanners mostly just work, offline (drivers are in the ISO closure,
  not downloaded on tick like LibreOffice).
- New network surface (Avahi/mDNS, cups-browsed, saned/AirScan): firewall opens
  5353/UDP + saned ports; CUPS stays localhost-only by NixOS default.
- The system stays free software unless the person turns the unfree drivers on
  (like the Drivers app's NVIDIA path); then unfree software is on for the whole
  system, explicit and reversible via `tulsi config`.
- Agents: printing/scanning remain human-initiated; Starah rules can gate agent
  access later (no silent print-to-exfiltrate/scan-to-upload).

## Verification

- `checks.printing-scanning` (Ocimum + Sonic nodes): cupsd/browsed/ipp-usb/avahi
  active, drivers in closure, `/etc/sane-config/airscan.conf` + `scanimage -V`,
  mDNS in nsswitch, 5353 open, `simple-scan`/`system-config-printer` on Ocimum,
  `skanlite` on Sonic.
- `checks.ocimum-desktop`: cupsd/browsed/ipp-usb/avahi active, AirScan conf,
  both apps, and no `cnijfilter2` by default.
- `checks.sonic-desktop`: cupsd/ipp-usb/avahi active, AirScan conf, skanlite.
- Installer `configuration.nix` carries `lp, scanner` groups; reference systems
  match.
