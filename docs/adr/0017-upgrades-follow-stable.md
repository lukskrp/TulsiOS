# ADR 0017: Installed machines follow the `stable` release branch

## Context

An installed machine builds itself from its system flake in `/etc/nixos` (ADR 0016).
Its `tulsi` input was a local path: the TulsiOS source the ISO carried, copied into
the store at install time. Everything else hangs off that source: tulsipkgs (the
kernel, the browser, security fixes), Starah and the modules, all pinned through
TulsiOS's own `flake.lock`. So an installed machine rebuilt itself fine, but always
on the release it was installed with. Nothing it had pointed at anything newer, and
once such machines exist, fixing that means editing every machine by hand. This had
to be settled before the first ISO is shared.

## Decision

- **Installed machines follow a release branch.** The system flake says
  `inputs.tulsi.url = "github:lukskrp/TulsiOS/stable"`. `stable` moves only when a
  release is cut (`docs/RELEASING.md`); `main` can change freely in between.
- **Installing stays offline.** `tulsi-install-system` writes `flake.lock` itself
  (`render.flake_lock`) instead of running `nix flake lock`:
  - the `tulsi` node is locked to the source the ISO carries: its git revision, its
    narHash and lastModified, which the TulsiOS flake passes from `self`
    (`tulsi.installer.sourceInfo`);
  - TulsiOS's own pins (tulsipkgs, Starah) are copied in from its flake.lock, with
    `follows` paths moved under `tulsi`, so the lock is complete and nothing rewrites
    it during `nixos-install`.

  Nix finds a locked input whose narHash is already in the store without
  downloading it, so the install needs no network, and `/etc/nixos` evaluates to
  exactly the installed system. (Checked first in a spike: a made-up revision with
  the real narHash evaluates with the network blocked.) A source tree with
  uncommitted changes has no revision; it is pinned by narHash with an all-zero
  revision, which only matters to a later upgrade.
- **Upgrading is an ordinary, undoable change.** tulsid's `Upgrade()` checks the
  branch, computes the moved `flake.lock` in a scratch copy (`nix flake update
  tulsi`), then runs the usual transaction: write it, rebuild, commit
  ("tulsi: upgrade TulsiOS 0.1.0 → 0.2.0"), restore it if the rebuild fails.
  `flake.lock` is now one of tulsid's managed files, so the upgrade is listed in
  History and `tulsi undo` takes it back. The old release's sources are still in the
  store, so undoing works offline (ADR 0014/0015). It has its own polkit action,
  `org.tulsi.upgrade`, because it changes the whole system at once.
- **The user decides when.** A daily user timer runs `tulsi upgrade --check --notify`:
  a new release is announced once, as a notification whose Upgrade button opens the
  Software Center's Updates page. Nothing upgrades on its own. `tulsi upgrade` does
  the same from a terminal; `tulsi upgrade --check` only reports.
- **One version number.** `VERSION` at the repository root is TulsiOS's version: the
  ISO's file name, Calamares' branding, `TULSIOS_VERSION` in `/etc/os-release`, and
  what `CheckUpgrade` reports for each side. `VERSION_ID` stays NixOS's release.
- **Development flakes are unchanged.** tulsid's bootstrap (the development VM) still
  writes a `path:` input; `CheckUpgrade` says such a system has no release branch.

## Consequences

- **Security fixes reach installed machines** through `stable`: a tulsipkgs fix is a
  `nix flake update nixpkgs` on main, then a release (or a patch release) to `stable`.
  The Attic cache (`cache.skarptech.org`) means machines download the result instead
  of building it.
- **`stable` must always build.** CI runs `nix flake check` on it as on main, and
  `docs/RELEASING.md` builds the ISO from the `stable` commit itself, so the ISO's lock
  carries a revision that exists on the branch.
- **Tests.**
  - `checks.tulsid`: a local git repository stands in for the branch; `CheckUpgrade`
    reports a new release, `tulsi upgrade` moves the lock and commits, `undo` restores
    it, a non-administrator is refused.
  - `checks.install-*`: the installed flake follows `stable`, its lock pins the carried
    source, `/etc/nixos` evaluates to the running system offline, and
    `tulsi upgrade --check` reports the release and the branch without a network.
  - A real upgrade over the network (and its rebuild) is checked by hand on an installed
    machine once `stable` has a second release.
- **A restart finishes an upgrade.** tulsid itself is not restarted during a switch
  (`restartIfChanged = false`), so the new tulsid and kernel run after a reboot; the
  Software Center says so.
