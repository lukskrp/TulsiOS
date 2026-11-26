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
  `gutenprint, gutenprintBin, hplip, splix, brlaser, cnijfilter2`.
- **Driverless:** `services.ipp-usb` (USB IPP/AirPrint/WSD as network devices)
  + `services.avahi` with `nssmdns4` and firewall open (mDNS discovery).
- **Scanning:** `hardware.sane` + `sane-airscan` backend, firewall open for
  network scanners.
- **Apps:** `simple-scan` + `system-config-printer` on Ocimum/dwm (Mint Cinnamon
  parity); `skanlite` + `system-config-printer` on SonicDE (`print-manager`
  stays as Sonic's frontend).
- **Unfree pre-accepted (Mint parity):** `nixpkgs.config.allowUnfree = mkDefault true`
  when the module is on. Covers `cnijfilter2`, `samsung-unified-linux-driver`,
  `hplipWithPlugin`, foomatic non-free DB. A person can harden again with
  `allowUnfree = mkForce false` + their own predicate.
- **Users:** installer `DEFAULT_GROUPS` + reference/VM users gain `lp, scanner`
  (USB scanner ACLs, CUPS admin).

## Consequences

- Printers/scanners mostly just work, offline (drivers are in the ISO closure,
  not downloaded on tick like LibreOffice).
- New network surface (Avahi/mDNS, cups-browsed, saned/AirScan): firewall opens
  5353/UDP + saned ports; CUPS stays localhost-only by NixOS default.
- Unfree, once pre-accepted, stays on for the whole system (like Drivers' NVIDIA
  path). Explicit, auditable, reversible via `tulsi config`.
- Agents: printing/scanning remain human-initiated; Starah rules can gate agent
  access later (no silent print-to-exfiltrate/scan-to-upload).

## Verification

- `checks.printing-scanning` (Ocimum + Sonic nodes): cupsd/browsed/ipp-usb/avahi
  active, drivers in closure, `/etc/sane.d/airscan.conf` + `scanimage -V`,
  mDNS in nsswitch, 5353 open, `simple-scan`/`system-config-printer` on Ocimum,
  `skanlite` on Sonic.
- `checks.ocimum-desktop`: cupsd/browsed/ipp-usb/avahi active, AirScan conf,
  both apps, `cnijfilter2` in closure (pre-accept proof).
- `checks.sonic-desktop`: cupsd/ipp-usb/avahi active, AirScan conf, skanlite.
- Installer `configuration.nix` carries `lp, scanner` groups; reference systems
  match.
