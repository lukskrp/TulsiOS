# ADR 0035: Media codecs and default apps

Status: accepted (2026-11-26). Amends ADR 0032 (the installer's "Extra software"
page) and ADR 0016 (the installer's offline reference systems).

## Context

Mint's promise is that media and documents just work. On TulsiOS:
- **Defaults were set on purpose only for text and the web.** PDFs, pictures, music,
  video and archives opened in whichever installed app claimed the type; on Ocimum
  pictures went to xviewer or pix by chance.
- **SonicDE and dwm had no viewer or player at all.**
- **There was no system-wide GStreamer.** Celluloid (mpv, ffmpeg) already played
  H.264, H.265, AV1 and MP3, but apps built on GStreamer (Rhythmbox, Elisa, Totem,
  …) played little. NixOS has no option for system-wide GStreamer plugins.
- **No DVDs, no RAR,** and no Microsoft fonts for documents made on Windows.

Some common formats are covered by software patents in a few countries, so the
person should be able to say no, but the default should be that things play.

## Decision

- **`tulsi.codecs.enable`** (`nix/modules/codecs.nix`):
  - GStreamer base, good, bad, ugly and libav in the system profile, with
    `pathsToLink /lib` (so the plugins land in `/run/current-system/sw/lib`,
    where `GST_PLUGIN_SYSTEM_PATH_1_0` points, and libdvdcss is discoverable)
    and `GST_PLUGIN_SYSTEM_PATH_1_0` pointing there;
  - libdvdcss (DVDs), unar (RAR) and 7-Zip.
  All of it is free software.
- **`tulsi.fonts.microsoft.enable`:** corefonts. They are unfree, so the option
  asserts `nixpkgs.config.allowUnfree`.
- **The installer:**
  - a **"Media"** page (`packagechooser@media`, required, default "Play all common
    media"; the other choice is "Patent-free formats only");
  - **"Microsoft fonts"** on the Extra software page, unticked, saying it turns on
    unfree software and needs the internet;
  - both are written into `configuration.nix` as settings, not into `state.json`, so
    `tulsi config` changes them and History undoes them;
  - the offline reference systems are built with codecs, so the default install still
    needs no network; the fonts are in `extras-cache`.
- **The Welcome window** has a **Media** page only when the codecs are off, with one
  button that turns them on through `tulsi config`.
- **Default apps per desktop** (`nix/modules/default-apps.nix`, `mkDefault`):

  | | Ocimum | SonicDE | dwm |
  | --- | --- | --- | --- |
  | PDF | xreader | Okular | zathura |
  | Pictures | xviewer | Gwenview | xviewer |
  | Camera RAW | pix | Gwenview | xviewer |
  | Music | Celluloid | Elisa | mpv |
  | Video | Celluloid | Celluloid | mpv |
  | Archives | File Roller | Ark | xarchiver |

  SonicDE and dwm now install these apps.
- **Rhythmbox** is on the Software Center's Featured page for people who want a
  music library on Ocimum.

## Consequences

- A default install plays every common format in every app, and DVDs and RAR open.
- Unticking "Media" gives a patent-free system that can be changed with one click.
- Ocimum has no music library by default; Celluloid plays music files, and Rhythmbox
  is one click away.
- dwm's xviewer cannot decode every RAW format (it has no libraw).
- `checks.codecs` proves that GStreamer decodes H.264, AAC and MP3 with the codecs
  and not without, that 7z archives open, and Ocimum's defaults.
