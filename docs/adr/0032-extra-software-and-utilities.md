# ADR 0032: LocalSend by default, and LibreOffice as an installer option

Status: accepted (2026-11-26). Amends ADR 0016 (the installer's pages) and ADR 0020
(what installs online).

## Context

TulsiOS came with a browser and its own apps, but little everyday software.

- **LocalSend:** sending a file from a phone to the computer, or between two
  computers, needed a cloud service or a cable. LocalSend does it on the local
  network, without an account, between Android, iOS, Windows, macOS and Linux.
- **LibreOffice:** most people need an office suite, but it is large (about 300 MB)
  and not everyone wants it. The ISO doesn't carry it.
- **Thanks:** the person wants people to see the work behind LibreOffice, and where to
  support it.

Tailscale was considered as a default and left out: people install it when they want
it.

## Decision

- **`tulsi.utilities`** (`nix/modules/utilities.nix`): on with every TulsiOS desktop
  (Ocimum, SonicDE, dwm), off on the live installer. It turns on
  `programs.localsend`.
  - The module opens LocalSend's ports (TCP and UDP 53317), because other devices
    can't find this one otherwise.
  - The wiki's "Sharing files and networks" page explains LocalSend, and how to
    install Tailscale (`tulsi service enable tailscale`, then `tailscale up`).
- **"Extra software" page in the installer:** a second `packagechooser` instance
  (`extras`, optional), after the desktop page. Its one item is LibreOffice, off
  unless ticked.
  - The item's text says it is downloaded during the installation, that it can also
    be installed later, and who makes it, with the donation page
    (https://www.libreoffice.org/donate/).
  - `tulsios-online` checks the TulsiOS cache before anything is written to the disk
    when LibreOffice is ticked, as it does for SonicDE. Without a connection it stops
    and says so.
  - `tulsi-install-system` adds the ticked extras to `/etc/nixos/tulsi/state.json`'s
    packages. LibreOffice is then an ordinary Software Center package: listed as
    installed, removable, and undoable.
  - The cache gets it like SonicDE: `extras-cache` (`nix/lib/extras-cache.nix`) is
    LibreOffice as an installed Ocimum system builds it. Each release pushes it
    (`docs/RELEASING.md`).
- **Donation links in the Software Center:** `donations.json` maps a project to its
  donation page. A "Donate" link sits next to Install/Remove for LibreOffice and its
  variants (Qt, unwrapped), whether or not it was installed from the installer.

## Consequences

- Every installed system runs with ports 53317 open on the local network, which
  LocalSend uses. Someone who doesn't want that sets
  `programs.localsend.enable = false;` with `tulsi config`.
- An install with LibreOffice needs the TulsiOS cache, as SonicDE does. If the cache
  lacks the release's LibreOffice, the install compiles it, which takes hours. Push
  `extras-cache` before publishing an ISO.
- More extras (or more donation links) are a line each: `render.EXTRAS`, the page's
  config, `ONLINE_EXTRAS`, `extras-cache`, and `donations.json`.

## Verification

- **Installer unit tests:**
  - the ticked extras are read from Calamares (string, list, empty);
  - unknown extras are refused;
  - `state.json` gets LibreOffice only when it is ticked;
  - the online check passes with the cache, stops without it before touching the
    disk, and names SonicDE and LibreOffice together.
- **Software Center unit test:** the donation link for LibreOffice's variants, and
  none for other packages.
- **The desktop VM tests:** LocalSend is installed on Ocimum, SonicDE and dwm; on
  Ocimum, its app-menu entry is there and the firewall opens 53317.
