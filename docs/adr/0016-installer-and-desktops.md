# ADR 0016: The installer, and a choice of two desktops

Status: accepted (2026-11-18)

## Context

Phase 7 (ROADMAP) is a Calamares ISO that installs TulsiOS. People should be able to
choose their desktop while installing:

- **Ocimum Desktop**, the default;
- **dwm**, for people who prefer a tiling window manager. dwm is plain X11, so it runs
  on XLibre (ADR 0009).

NixOS already has a Calamares setup (`calamares-nixos-extensions`, in tulsipkgs). Its
`nixos` job writes a classic `configuration.nix` and runs `nixos-install`. TulsiOS
systems are different: they are a flake in `/etc/nixos` that tulsid manages. Until now,
tulsid's bootstrap generated that flake on first boot, and only for the development VM
(`nix/hosts/vm`).

## Decision

### Installed machines are the system flake, from the first boot
- **Host module.** `nix/hosts/desktop` is the host module for installed machines. It
  turns on the Software Center, the Assistant, tulsid with bootstrap, NetworkManager,
  PipeWire, printing and Bluetooth.
- **What is written per machine.** Everything that differs per machine goes into
  `/etc/nixos`:
  - `configuration.nix`: hostname, users, locale, keyboard, boot loader and
    `tulsi.desktop.session`;
  - `hardware-configuration.nix`;
  - `tulsi/state.json`, starting with `state/initial.json` (Firefox).
- **One template.** `data/system-flake.nix.in` is the single flake template. tulsid's
  bootstrap and the installer both fill it in. The flake imports
  `hardware-configuration.nix` when it exists, so `configuration.nix` holds no
  `imports` or paths, which ADR 0014 would treat as code.
- **Locales.** `i18n.supportedLocales` defaults to all locales. They are prebuilt, so no
  language choice forces a glibc locale build during an offline install.

### `tulsi-install-system` does the installing
- **What it does:** a small Python program (`apps/tulsi-installer`) that takes the answers,
  validates them, writes the files above, and runs
  `nixos-install --flake /mnt/etc/nixos#<host>`.
- **Validation:**
  - names and keymaps are checked against strict patterns;
  - strings are escaped for Nix;
  - the output is checked with `nix-instantiate --parse` in its tests.
- **Who calls it:** Calamares and the VM tests both call it, so the GUI only collects
  answers and the install logic is tested without a GUI.
- **Offline install.** nixos-install needs no network, for three reasons:
  - `tulsi.installer.offlineSystems` keeps reference installs' closures in the live
    system's store.
  - The answers only change small files (hostname, fstab, users, time zone, keyboard).
    Everything above them is rebuilt too: /etc and its unit trees, the system profile,
    the initrd and the toplevel. Those rebuilds need their inputs, and a runtime closure
    doesn't carry them all:
    - the initrd is compressed, so it keeps no references;
    - buildEnv drops shadowed packages;
    - `xkbvalidate` is a build-time tool.

    `nix/lib/offline-rebuild-inputs.nix` keeps them: for each of those derivations it
    writes its attributes to a file, and that file references every input. Plain
    `inputDerivation` misses inputs passed through files or structured attributes.
    `nix/lib/install-closure.nix` adds the generic build tools, as nixpkgs' installer
    test does.
  - `tulsi-install-system` passes `always-allow-substitutes`. Without it, Nix rebuilds
    trivial builders (`allowSubstitutes = false`, e.g. buildEnv) even though the live
    store has them. That drags in their build-time inputs, and in the end the whole
    bootstrap toolchain.

  `checks.install-*` installs build exactly the per-machine derivations (38 of them) and
  copy everything else from the live store.

### Calamares, only on the live ISO
- **Package.** `calamares-tulsios-extensions` reuses upstream's settings for locale,
  keyboard, users, partitioning and mounting, and replaces:
  - the `nixos` job with a thin `tulsios` job. It dumps Calamares' answers as JSON (without
    LUKS passphrases) and runs `pkexec tulsi-install-system --calamares …`, turning Nix's
    log into progress;
  - the desktop page, with two items, Ocimum Desktop (default) and dwm;
  - the welcome checks (the internet is checked but not required);
  - the branding and slideshow.
- **Dropped:** upstream's "allow unfree" page, because TulsiOS accepts licences per package
  (ADR 0012).
- **Qt stays on the ISO.** Calamares is Qt 6 with KPMcore and runs only there; installed
  systems stay free of Qt (as with the login screen, ADR 0010).

### The live ISO
- **What it is.** `nixosConfigurations.tulsi-iso` (`nix build .#iso`) is nixpkgs'
  graphical installer base plus `nix/hosts/iso/live.nix`: Ocimum Desktop, logged in as
  `nixos`, with Calamares started at login (as root, through pkexec). Starah's first-login
  setup and adopt hints are off; tulsid, the Software Center and the Assistant are off too,
  since nothing on a system in RAM needs undoing. It is a hybrid ISO, so `dd` or Etcher
  onto a USB stick gives the same image for BIOS and UEFI machines.
- **Offline, on any hardware.** The ISO carries two reference installs
  (`nix/hosts/iso/references.nix`, `nix/lib/reference-system.nix`): Ocimum with
  systemd-boot and dwm with GRUB, so between them both desktops and both boot loaders.
  They switch on what a real machine's `hardware-configuration.nix` and Calamares'
  answers may need: every disk controller module (`hardware.enableAllHardware`), both CPU
  vendors' microcode, ext4/btrfs/xfs/f2fs, LUKS and Hyper-V guest support. The machine's
  own initrd, udev rules and boot entries are then rebuilt from what is in the store.
- **Names.** All TulsiOS systems call themselves TulsiOS in `/etc/os-release`
  (`ID=tulsios`, `ID_LIKE=nixos`), `/etc/issue` and boot menus (`nix/modules/branding.nix`).
  The ISO's boot menus use the Tulsi Leaf wallpaper, and Plymouth shows the TulsiOS logo.

### dwm: suckless dwm 6.8 with one patch, the system tray
- **Choosing a desktop.** `tulsi.desktop.session = "ocimum" | "dwm"` picks the desktop.
  Only the chosen one is installed; switching later is one line.
- **The patch.** dwm gets exactly one patch, the systray patch (`data/dwm/dwm-systray-6.8.diff`).
  Upstream's 6.8 patch needed three hunks ported to the 6.8 release tarball.
- **Keys.** TulsiOS's `config.h` keeps dwm's keys with Super as the modifier, and adds:
  - Super+A for the Assistant;
  - Super+S for the Software Center;
  - Super+Shift+L for slock.
- **What Cinnamon would otherwise provide**, `tulsi.dwm` turns on:
  - XDG autostart and `graphical-session.target`, which start Starah's session helper and
    the extension watcher;
  - a polkit agent;
  - dunst for notifications;
  - nm-applet in the tray, in XEmbed mode, because the patch shows no indicators;
  - slstatus;
  - the GTK theme (Mint-Y-Dark) through `/etc/xdg/gtk-3.0/settings.ini`.
- **Login.** Both desktops log in through the Ocimum Greeter on XLibre, and both get Starah
  and the TulsiOS way of installing software (ADR 0013).

## Consequences

- **Tests.**
  - `checks.install-dwm` and `checks.install-ocimum` partition a disk, install offline with
    `tulsi-install-system`, and boot the disk through its own systemd-boot. They then check
    that only the chosen desktop is there, that the greeter logs into it, and that
    `/etc/nixos` evaluates to exactly the running system.
  - `checks.dwm-session` checks the dwm session's pieces.
  - The ISO is tested in layers, each where it is cheap, so a test never waits on a
    squashfs it does not need:
    - `checks.live-session`: the live session in an ordinary VM (minutes), with Calamares
      running and its welcome page passing its checks;
    - `checks.install-iso-references`: an offline install with the ISO's own reference
      installs onto QEMU hardware they were not made for, in a combination neither has
      (dwm with UEFI). It builds the machine's kernel module set, initrd and boot entries
      (53 derivations) and copies the rest;
    - `checks.iso-boot`: the ISO itself boots on UEFI and on BIOS into the live session
      with Calamares (about 12 minutes, the ISO build included).
  - The Calamares pages themselves are clicked through by hand, in Hyper-V Gen 2 with the
    release ISO, once per desktop.
- **Found on the way.** The Ocimum Greeter's session launcher replaced the session's
  `PATH`, so sessions had no `/run/wrappers/bin`: pkexec and sudo were the unprivileged
  store binaries ("pkexec must be setuid root"). The launcher now hands the session the
  login `PATH`, and `checks.live-session` checks it.
- **Known limits of the ISO.** It is not signed for Secure Boot (turn Secure Boot off).
  The VirtualBox guest module is an out-of-tree kernel module, which an offline install
  cannot build; installs inside VirtualBox need a network for it.
- **Rebasing.** dwm releases need the systray patch rebased. dwm changes rarely, and the
  patch is the one most dwm users run.
- **Artwork.** The wallpaper and the TulsiOS logo live in Ocimum Desktop's sources.
  - Calamares takes the logo from `cinnamon.src` (the sources, not the build).
  - A dwm install shows a plain background until the artwork moves into a package of its
    own, so the wallpaper does not bring Cinnamon along.
- **Upgrades** (decided in ADR 0017). Installed flakes follow the `stable` branch
  (`github:lukskrp/TulsiOS/stable`), pinned at install time to the source the ISO
  carries, so installing stays offline; `tulsi upgrade` and the Software Center's
  Updates page move to newer releases, and undo takes an upgrade back.
