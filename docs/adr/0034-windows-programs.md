# ADR 0034: Windows programs (Bottles, Lutris)

Status: accepted (2026-11-26). Amends ADR 0032 (the installer's "Extra software"
page) and ADR 0018 (the "Install the TulsiOS Way" window).

## Context

People bring Windows programs and games. On TulsiOS a downloaded `.exe` or `.msi`
reached nothing:
- no MIME handler claimed it;
- `tulsi inspect` called it unknown;
- the Install the TulsiOS Way window called it an archive, and ended with "no recipe
  fits".

The person wanted a graphical way to run Windows programs with Wine and Proton, and
prefers Bottles.

**The options in tulsipkgs:**

| App | Strength | Against |
| --- | --- | --- |
| Bottles 67.7 | Any Windows program: isolated bottles, managed runners (Wine, Soda, Proton-GE), dependencies, snapshots | GTK4/libadwaita (ignores TulsiOS themes); about 1 GB with its runtime; upstream supports only its Flatpak |
| Lutris 0.5.22 | Games: GOG, Epic, Steam, Humble, emulators, community scripts | Weaker for everyday programs |
| Heroic | Epic, GOG, Amazon games | Electron; games only |
| Faugus Launcher, umu-launcher | Simple Proton runs | Few features; umu has no window |
| Steam | Steam games with Proton | Unfree; already possible via `programs.steam` |

## Decision

- **Bottles for Windows programs, Lutris for games, Steam stays as it is.** None is
  installed for everyone (they are large).
- **The installer's "Extra software" page** offers Bottles and Lutris next to
  LibreOffice. Lutris is `lutris-free`: nixpkgs' `lutris` bundles Steam, which is
  unfree and would need unfree software turned on. Steam games still work once
  Steam is installed (`programs.steam`).
  - The page is now `optionalmultiple`, so any combination can be ticked.
  - They download from the TulsiOS cache (`extras-cache`, pushed with
    `--ignore-upstream-cache-filter`). `tulsios-online` checks the cache first.
  - Bottles' text says Windows programs run as the person, and links its funding
    page.
- **A Featured page, first in the Software Center** (`featured.json`): Office
  (LibreOffice), Windows programs and games (Bottles, Lutris), and Everyday (VLC,
  Thunderbird, GIMP, Inkscape, Krita, OBS Studio).
  - Installed state and Donate links work as on the other pages.
  - `checks.ai-agents-index` also checks that every featured package is in the index
    and free.
- **Opening a .exe or .msi:**
  - `tulsi inspect` has a `windows` kind: an `MZ` header, or an OLE file named
    `.msi`.
  - `tulsi.adopt` handles `application/x-ms-dos-executable`,
    `application/x-msdownload`, `application/x-msi` and `application/x-ms-installer`.
  - The window then says it is a Windows program and offers **Open with Bottles**
    (`bottles FILE`, whose bottle picker asks where to run it) or **Install Bottles
    to Run This**, with the warning that Windows programs run as the person. It
    doesn't look up or package anything.
  - Recipes refuse the kind ("run it with Bottles").
- **Bottles' "unsupported build" notice stays:** it is true, and the wiki says to
  report problems to TulsiOS.
- **Wiki "Windows programs":** what to use for what, Bottles' bottles and snapshots,
  Steam through `tulsi config`, and the warning.

## Consequences

- **No sandbox:** Windows programs have the person's files, like any program they run.
  Bottles' Flatpak confinement isn't available here. Starah doesn't cover them; they
  aren't agents.
- **A themes exception:** Bottles brings GTK4 and libadwaita; its windows don't follow
  TulsiOS's themes.
- **Cache size:** the cache grows by Bottles' and Lutris' closures, pushed per release.

## Verification

- `tulsi-inspect`: PE and `.msi` files are Windows; an OLE `.doc` isn't; names come
  from Windows file names.
- **Installer tests:** several extras at once; the online check names Bottles and
  Lutris.
- **Software Center tests:** the featured list; Windows files go to "open with
  Bottles", or "install Bottles" when it's missing.
- **The index check:** featured packages exist and are free.
- **VM checks:** `software-center`, `adopt`, `vm-toplevel`.
