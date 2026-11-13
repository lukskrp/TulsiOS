# ADR 0009: X11 with XLibre, OTK's own rendering engine, OpenMandriva's systemd

Status: accepted (2026-11-12)

## Context

Cinnamon 6.8 can run as a Wayland session, and its background daemon was written for
GTK 4 with a Wayland layer-shell painter. TulsiOS's toolkit is GTK3-O and OTK (ADR 0005,
ADR 0008), and the project wants its own direction for the display stack and init system.

## Decision

- **Display server: XLibre**, the X.Org fork. It is TulsiOS's only supported display
  server; neither Xorg nor Wayland is a target. Ocimum Desktop is built with
  `-Dwayland=false`; the Wayland code stays in its tree, unbuilt. XLibre has no
  fractional scaling yet; that is future work. XLibre is packaged in tulsipkgs as its
  own track.
- **OTK takes features from GTK 4** where they are worth having, behind the
  `GDK_AVAILABLE_IN_OTK_n` markers and `OTK_API_VERSION`. OTK 1 (2026-11-12): the monitor
  list model, connector names, `gdk_monitor_get_scale()`, `gtk_disable_portals()`, and
  `g_autoptr()` for the newer GDK types. That let Cinnamon's background daemon move
  from GTK 4 to OTK.
- **OSK, the Ocimum Scene Kit:** GTK 4's rendering engine (GSK render nodes, the Cairo
  and GPU renderers, GdkTexture/GdkPaintable, GtkSnapshot) is ported into OTK as a
  separate, optional library (`libosk-3`, `osk-3.0`, `Osk-3.0`), keeping the `gsk_*` names
  so GTK 4 code ports easily. Stages: core + Cairo renderer; widget `snapshot` with
  `OTK_RENDERER=legacy|cairo|gl`; the GL renderer on X11; later Vulkan and TulsiOS's own
  tuning.
  *Stage 1 done 2026-11-13:* OTK `3.24.52-otk.3` ships `libosk-3` built from GTK
  4.24.0 (render nodes, `.node` format, textures, colour states, Cairo renderer);
  OSK's `GdkSurface` is ODK's `GdkWindow` and `GdkRGBA` keeps ODK's double components.
- **systemd from OpenMandriva** (`github.com/OpenMandrivaAssociation/systemd`): nixpkgs'
  systemd at OpenMandriva's version with their patches that apply outside RPM, installed
  through NixOS's `systemd.package`, so packages linking libsystemd keep coming from
  cache.nixos.org.

## Consequences

- Wayland-only features (layer shell, fractional-scale-v1) are not ported to OTK.
- OTK keeps GTK 3's API and source compatibility; OTK-only API is additive until OSK's
  widget stage, which changes `GtkWidgetClass` (allowed: OTK breaks ABI by design).
- XLibre and the OpenMandriva systemd each need their own packaging and tests before
  TulsiOS switches to them.
