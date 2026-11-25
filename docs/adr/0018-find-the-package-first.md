# ADR 0018: Find the package first; recipes before the Assistant

Status: accepted (2026-11-23). Implemented:
- Milestone 1: matching.
- Milestone 2: Recipes, the choice between Recipes and the Assistant, kept downloads.
- Milestone 3: the step-by-step window, and "Install from a File or Link…".

## Context

ADR 0013 sends every imperative install attempt to `tulsi-adopt`. Matching there was a
single fuzzy search on a name guessed from the file name:
- **A renamed download matched nothing.** `download.deb` gave the guess `download`;
  its own name, inside the package, was never read.
- **Other systems' names matched nothing.** `apt install python3-requests`,
  `libfoo-dev` and `build-essential` are not nixpkgs names, and `apt install
  openssh-server` is a service on NixOS, not a package.
- **Programs were not a clue.** A `.deb` containing `/usr/bin/cvlc` is VLC, but
  nothing looked inside.
- **Some installers were not intercepted at all:** `pip install`, `npm install -g`,
  `cargo install`, `go install`, `gem install`, `flatpak install`, `.flatpakref`
  files and links to extension store pages.
- **A failed lookup looked like "nothing matched",** which sent people to the
  Assistant for software TulsiOS already has.

Whatever is not matched ends with the Assistant writing a whole Nix expression. That
needs a model, a network connection or a local model, and the person's trust. TulsiOS
should be able to install software without a model whenever it can.

## Decision

**Matching comes first and needs no model.** tulsid's new `Match(hint, limit)` method
takes what someone tried to install, as `{names, programs, provides, tool}`. It returns
packages or services, each with a reason people can read. The order:
1. **The curated table** of other systems' names (`data/name-map.json`): for example
   `build-essential` → gcc and gnumake, `code` → vscode, `openssh-server` → the openssh
   service. It only lists services that `setService` (`services.<name>.enable`) can
   switch on by itself.
2. **The name as a package:**
   - an exact attribute;
   - the tool's package set: `pip` → `python3Packages.x`, `npm` → `nodePackages.x`,
     `gem` → `rubyPackages.x`;
   - other distributions' naming rules: `python3-x`, `node-x`, `r-cran-x`,
     `golang-x`, `-dev`/`-devel`/`-bin` suffixes, `lib` prefixes with soname digits;
   - then an exact pname.
3. **The programs inside the download,** or the name as a command, in the **program
   index** (`nix/packages/program-index.nix`).
   - The index is built from nix-index-database's small database: the programs in
     `bin/` of what Hydra builds. That file is downloaded with a pinned hash, not taken
     as a flake input.
   - tulsid drops attributes its package index does not have.
4. **A fuzzy search** on the first name, last.

**Downloads are recognised by their content.** The new crate `tulsi-inspect` (`tulsi
inspect FILE`) reads:
- the file kind, from its first bytes;
- a `.deb`'s control file and the programs in its `bin` directories;
- an `.rpm`'s header, parsed without the rpm tools;
- a `.flatpakref`'s application;
- an archive's executables.

tulsi-mcp's `fetch_source` uses the same code.

**More entry points.**
- `pip`, `pip3`, `pipx`, `npm`, `cargo`, `gem`, `go` and `flatpak` are shims. Only
  their install commands (`npm install` only with `-g`) go to `tulsi-adopt`;
  everything else runs the real tool when one is on PATH. The shims have low priority,
  so installing the real tool system-wide replaces them.
- `.flatpakref` files open the popup. TulsiOS does not install Flatpaks; it offers the
  Nix package.
- `tulsi-adopt --url` and the Software Center's Extensions page ("Add by Link") take a
  link to an extension's store page:
  - a Chrome Web Store link carries the extension's id;
  - a Firefox Add-ons link is looked up on addons.mozilla.org, which needs a network
    connection.

**The popup and the shims tell what happened.**
- Each match shows its reason, and a service match offers "Turn On" (the Software
  Center's new `service` action).
- A shim in a terminal lists the matching `tulsi install` and `tulsi service enable`
  commands.
- When tulsid cannot be asked, both say so instead of "nothing matched".

**Recipes, then the Assistant (Milestone 2).** When nothing matches, the popup
offers two ways to package the software, so a computer with no AI model at all can
still install the common downloads:
- **Package It with a Recipe** (crate `tulsi-recipes`, `tulsi recipe plan|build|install`):
  - Tested templates turn the inspected file and a few answers into a local package:
    - AppImages (`appimageTools.wrapType2`, with their menu entry and icon);
    - one prebuilt program;
    - prebuilt programs in .deb, .rpm, tar and zip files (`autoPatchelfHook`, links
      and menu entries pointing into the package, Electron's run-time libraries);
    - source built with CMake, Meson, autotools, make, Cargo or Go.
  - The answers: name, version, main program, licence, menu entry, and keeping the
    download.
  - It builds as the person, in Nix's sandbox, against the system's pinned nixpkgs.
    It fixes what it can by itself and builds again:
    - libraries a program needs, from `data/sonames.json`; libraries nothing provides
      are left out, with a warning;
    - build dependencies, from `data/pkg-config-names.json`;
    - a Rust or Go program's dependency hash.
  - It then tries the main program in a bubblewrap sandbox: the read-only Nix store
    and an empty home, no network, none of the person's files. Without a sandbox the
    program is not run.
  - The package passes the same `check_expression` as the Assistant's. It is
    installed through the Software Center (`apply-ops`) with its confirmation,
    history and Undo, as `addLocalPackage`. A licence the person accepts as
    proprietary goes with it (`acceptLicense`).
- **Ask the Assistant:** as in ADR 0013. It is shown as needing an AI model when none
  is set up; Recipes are then the suggested way. If a Recipe fails, the Assistant
  gets the Recipe's draft and the build log.

The choice can be remembered:
- **Where:** `~/.config/tulsi/packaging.json`, `whenNoPackage`: ask, recipe or assistant.
- **How it is set:** with "Remember my choice" in the popup, or in Starah's window.
- **What it does:** when nothing matches at all, the remembered way starts by itself.

**Keeping the download (a choice, on by default).** A local package made from a
downloaded file needs that file whenever it is built again, after an upgrade for
example, and TulsiOS cannot download it again.
- **Where it is recorded:** state.json `keepSources` lists the packages whose download
  is kept.
- **How it is kept:** the `tulsi.state` module adds each kept package's `src` to
  `system.extraDependencies`. The file lives as long as a system generation has it,
  so Undo, rollback and Nix's cleanup all stay consistent.
- **How it is chosen:**
  - by default, through `addLocalPackage`'s `keepSource`;
  - in the Recipe dialog;
  - later, on the Software Center's Installed page (`keepSource` op) or with
    `tulsi keep-source NAME on|off`.

**A step-by-step window (Milestone 3).** `tulsi-adopt` is a wizard (`wizard.py`) with
six steps:
1. What it is
2. In TulsiOS
3. How to package it
4. Details
5. Build and try
6. Install

It has a step bar, Back and Next, and Enter goes on. Steps that do not apply are
skipped:
- **A match:** the window opens straight on the matches, and installing one ends
  there. "What it is" stays first for downloads that need packaging.
- **A remembered choice** skips "How to package it" when nothing matches.
- **Asking the Assistant** ends the window.

The Software Center's "Install from a File or Link…" (Search page, and the action
`install-file`) opens the same window for a chosen file or a pasted link.

## Consequences

- **More is found without a model.** `apt install python3-requests`, a renamed `.deb`
  of VLC, `pip install requests` and `apt install openssh-server` all lead to
  TulsiOS's own packages or services.
- **The program index can lag tulsipkgs slightly.** It follows nixpkgs-unstable's
  Hydra builds, and only lists what Hydra builds, so unfree packages are missing.
  Attributes tulsipkgs lacks are dropped; a program tulsipkgs adds is found once
  nixpkgs has it. The database is updated by bumping its release and hashes.
- **The curated table needs care.** Wrong entries only cost a wrong suggestion, which
  the person sees before installing. Unknown attributes are filtered out.
- **Developers keep their tools.** `pip install` inside a virtualenv, `npm install` in
  a project and `cargo build` reach the real tools, which come first on PATH.
- **Installing system-wide is still the only scope** (state.json `packages`).
- **Recipes have limits.**
  - Software outside the templates, unusual layouts, Python projects, installer
    scripts and source builds that need libraries the tables do not know stay with
    the Assistant.
  - A prebuilt program may still miss a library it only loads at run time; a warning,
    the sandboxed try or the program itself says so.
  - Qt applications are not wrapped (`wrapQtAppsHook`) yet.
  - A failed Recipe's draft can be finished by hand in the Nix Editor (ADR 0019).
- **Kept downloads take disk space.** They do so while any generation keeps them, which
  is why keeping them is a choice per package.
