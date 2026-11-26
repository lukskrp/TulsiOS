# Media and files

## What opens what

| | Ocimum Desktop | SonicDE | dwm |
| --- | --- | --- | --- |
| PDF | Xreader | Okular | zathura |
| Pictures | Xviewer | Gwenview | Xviewer |
| Camera RAW photos | Pix | Gwenview | Xviewer |
| Music | Celluloid | Elisa | mpv |
| Video | Celluloid | Celluloid | mpv |
| Archives (ZIP, 7z, RAR, tar) | File Roller | Ark | Xarchiver |

To open a kind of file with another app every time, right-click a file of that kind,
choose **Open With → Other Application**, pick the app and tick **Set as default**
(in Ecco on SonicDE: **Open With → Other…**, then **Remember application
association**).

Want a music library with albums, playlists and podcasts? Install **Rhythmbox** from
the Software Center (it is on the Featured page).

## Codecs

During installation the **Media** page asks whether to play all common formats.
With the default, "Play all common media", every app plays MP3, AAC, H.264, H.265
and the other common formats, DVDs play, and RAR and 7z archives open.

If you picked "Patent-free formats only", the video player still plays most
videos, but other apps may not play MP3 or MP4 files. To turn the codecs on later,
open the **Welcome** window and its **Media** page, and click **Turn On Codecs**.
Or add this to your configuration with `tulsi config`:

```nix
tulsi.codecs.enable = true;
```

Turning them off again is the same line with `false`, or undo the change in the
Software Center's **History**.

## Microsoft fonts

Documents made on Windows often use Arial, Times New Roman or Verdana. Without
them, LibreOffice uses look-alike fonts, so pages can break differently. The
installer's **Extra software** page offers **Microsoft fonts**; later you can add
them with `tulsi config`:

```nix
tulsi.fonts.microsoft.enable = true;
nixpkgs.config.allowUnfree = true;
```

These fonts are not free software, so they need unfree software turned on (the
second line).

