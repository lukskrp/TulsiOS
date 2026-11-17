# ADR 0013: Install the TulsiOS way

Status: accepted (2026-11-17)

## Context

People arrive at TulsiOS with habits from other distributions. They type `apt install`,
download a `.deb`, `.rpm`, AppImage or tarball, or run a program built elsewhere. On
NixOS, all of these fail with an unhelpful error, or work imperatively and are lost on
the next rebuild. The declarative alternative, writing a Nix expression, is exactly
what most people cannot do.

TulsiOS already has the pieces for a better answer:
- the Software Center and tulsid, with history and Undo;
- the Assistant and tulsi-mcp, with mandatory approval (ADR 0004);
- Starah's privilege levels for agents (ADR 0011).

## Decision

**Every imperative install attempt opens `tulsi-adopt`, "Install the TulsiOS Way"**
(`tulsi.adopt`, on by default with the Software Center):
- **Package commands.** `apt`, `apt-get`, `dnf`, `yum`, `pacman`, `zypper`, `snap` and
  `brew` are shims. They explain the TulsiOS way, name the matching `tulsi install`
  command and open the popup in a graphical session. They always exit 1, so scripts
  notice that nothing was installed.
- **Downloaded files.** `tulsi-adopt` is the default handler for downloaded packages and
  archives: .deb, .rpm, AppImage, tarballs, zip and .run.
- **Foreign binaries.** NixOS's ELF-loader stub (`/lib64/ld-linux-x86-64.so.2`) is replaced
  by one that still prints the stub's message and exits 127, but also opens the popup with
  the program. This is turned off with `tulsi.adopt.foreignBinaries` when nix-ld is used.

**The popup offers the matching Software Center packages first.** If nothing fits, it
offers **"Ask the Assistant to Package It"**, which takes these steps:
- The Assistant runs as the Starah agent `assistant` and uses new tulsi-mcp tools:
  - `fetch_source` downloads a URL, or takes the file already added to the store, and
    describes it: kind, hash, contents and build hints.
  - `build_package` saves a `callPackage` expression as a draft in the agent's workspace
    and builds it in Nix's sandbox against the system's pinned nixpkgs
    (`/etc/tulsi/nixpkgs`).
  - `try_package` runs the result briefly, with an empty home and no display.
  - `propose_local_package` asks a person, who sees the whole expression.
- After approval, tulsid writes a **local package** to the system flake:
  - `/etc/nixos/tulsi/pkgs/<name>/package.nix` and `meta.json` (version, description,
    origin);
  - `localPackages` in state.json, through the new ops `addLocalPackage` and
    `removeLocalPackage`.
- `tulsi.state` builds each local package with `pkgs.callPackage`, without an overlay, and
  installs it. The Software Center lists it under "Made on this computer". The change goes
  through history and `tulsi undo` like any other.
- Because the rebuild evaluates the expression as root, tulsi-state checks it before
  building and before applying, on top of the person's review. The check refuses host
  reads, impure fetches, sandbox escapes and oversized expressions. Downloads must be
  fixed-output (hashed).

**Sharing back to tulsipkgs comes later and is opt-in.** A local package stays on the
machine unless its owner chooses to contribute it.

## Consequences

- `apt install vlc` leads to a declarative VLC in two clicks. Software that nobody has
  packaged becomes a reproducible package that survives rebuilds and can be undone.
- **Mistakes are contained.** Agent-written expressions build in Nix's sandbox, as the
  agent's account. Nothing is installed without a person's approval or a Starah level
  that allows it.
- **Licences of local files.** `requireFile` assumes unfree software. Expressions for
  downloaded files must set `meta.license`, or the package is refused like any other
  unfree package (ADR 0012). The Assistant's hints tell it so.
- **Not everything packages cleanly.** Proprietary binaries need `autoPatchelfHook`, and
  some need FHS environments. The Assistant may fail, and then says so; nothing changes.
- **Scripts that call `apt`** now get a clear failure instead of "command not found".
