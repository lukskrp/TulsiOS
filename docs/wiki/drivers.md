# Drivers

**Drivers** (in the app menu, under Settings) shows the graphics cards, Wi-Fi cards
and processor in your computer, the driver each one uses, and the other drivers you
can choose. In a terminal, `tulsi-drivers list` shows the same.

## What you may want to change

- **NVIDIA graphics cards** work out of the box with **Nouveau**, the open-source
  driver. NVIDIA's own driver is faster in games, and is needed for CUDA, NVENC and
  most AI tools. Drivers recommends the right one for your card:
  - GeForce GTX 16xx, RTX 20xx and newer: NVIDIA's current driver, with its open
    kernel modules.
  - GeForce GTX 9xx and 10xx: NVIDIA's 580 series, the last for these cards.
  - GeForce GTX 6xx and 7xx: NVIDIA's 470 series.
  - Older cards: only Nouveau. NVIDIA's last drivers for them don't work with
    TulsiOS's Linux.
- **Laptops with two graphics chips** (Intel or AMD, plus NVIDIA) get two choices:
  - **Power saving** (recommended): the built-in graphics draw the desktop, and the
    NVIDIA card runs only the apps you start with right-click › **Run with dedicated
    GPU**, or `nvidia-offload app` in a terminal. Best for battery life.
  - **For everything**: the NVIDIA card draws everything. Faster, uses more battery.
- **AMD and Intel graphics** need no changes. You can add:
  - **Hardware video decoding** (Intel): smoother videos that use less battery.
  - **Compute** (OpenCL, ROCm or Level Zero), for apps like Blender and Darktable.
  - **Use amdgpu instead of radeon**, for Radeon HD 7000 to R9 290 cards.
- **32-bit graphics libraries**, for Steam and older games.
- **Broadcom Wi-Fi cards** that the open drivers don't support can use Broadcom's
  **STA** driver. It is unmaintained and has known security problems, so use it
  only when your Wi-Fi doesn't work otherwise.

The processor's row says whether its **microcode updates** (fixes from Intel or AMD)
load at every start. They do by default.

## Unfree drivers

NVIDIA's and Broadcom's drivers are *unfree*: you can use them, but not see or change
their code. Choosing one asks you to accept its licence, and turns on unfree software
for the whole system. From then on, the Software Center can install unfree apps too.

## Restarting with new drivers

A driver change takes effect when you **restart**. Drivers builds the new drivers
first, which takes a few minutes, then offers **Restart Now**.

After the restart, TulsiOS asks **"Do your new drivers work?"**:

- **Keep** if the screen, the Wi-Fi and everything else work.
- **Go Back** returns to the drivers you had before, from the next restart.

## If the screen stays black

Don't worry: the drivers before are still there.

- On most computers (those that start with UEFI), **restart again**. Hold the power
  button for a few seconds if nothing responds. The new drivers start only once
  until you keep them, so this start uses the drivers before, and TulsiOS undoes
  the change by itself.
- On older computers (those that start with BIOS), wait ten minutes, then restart.
  A change nobody keeps within ten minutes is undone. Or pick the previous entry
  in the boot menu.

You can also switch to a text console with **Ctrl+Alt+F3**, log in, and run
`tulsi-drivers undo`, then restart.

Afterwards, TulsiOS tells you that the change was undone. The Software Center's
History lists both the change and its undo.

## In a terminal

```sh
tulsi-drivers list              # devices, drivers, and the choices (ids)
tulsi-drivers recommend         # what TulsiOS recommends for this computer
tulsi-drivers set nvidia        # choose; or `set recommended`, `set --off games32`
tulsi-drivers status            # what is chosen, and a change waiting on a restart
tulsi-drivers keep              # keep the drivers you restarted with
tulsi-drivers undo              # go back
```

Your choices are kept as `tulsi.drivers.*` settings in a marked block of
`/etc/nixos/configuration.nix`. Change them in Drivers rather than by hand.
