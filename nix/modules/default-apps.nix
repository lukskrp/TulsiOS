# What opens what, on each TulsiOS desktop (ADR 0035).
#
# Without this, PDFs, pictures, music, video and archives open in whichever
# installed app happens to claim the type, and SonicDE and dwm have nothing for
# them at all. Each desktop gets a viewer or player for each, chosen on purpose
# (mkDefault: a person's own choice in their settings still wins, and so does a
# machine's configuration.nix).
#
# - Ocimum: xreader, xviewer, pix (camera RAW), Celluloid, File Roller (Cinnamon's).
# - SonicDE: Okular, Gwenview, Elisa (music), Ark, and Celluloid for video.
# - dwm: zathura, xviewer, mpv, xarchiver.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  pdf = [ "application/pdf" ];
  images = [
    "image/jpeg"
    "image/png"
    "image/gif"
    "image/webp"
    "image/bmp"
    "image/tiff"
    "image/heif"
    "image/avif"
    "image/svg+xml"
  ];
  raw = [
    "image/x-canon-cr2"
    "image/x-canon-cr3"
    "image/x-nikon-nef"
    "image/x-sony-arw"
    "image/x-fuji-raf"
    "image/x-olympus-orf"
    "image/x-panasonic-rw2"
    "image/x-adobe-dng"
    "image/x-dcraw"
  ];
  audio = [
    "audio/mpeg"
    "audio/mp4"
    "audio/aac"
    "audio/flac"
    "audio/ogg"
    "audio/x-vorbis+ogg"
    "audio/opus"
    "audio/x-wav"
    "audio/x-m4a"
  ];
  video = [
    "video/mp4"
    "video/x-matroska"
    "video/webm"
    "video/quicktime"
    "video/x-msvideo"
    "video/mpeg"
    "video/ogg"
  ];
  archives = [
    "application/zip"
    "application/x-7z-compressed"
    "application/vnd.rar"
    "application/x-rar"
    "application/x-tar"
    "application/x-compressed-tar"
    "application/x-xz-compressed-tar"
    "application/x-bzip2-compressed-tar"
    "application/x-zstd-compressed-tar"
    "application/gzip"
  ];

  # { types = app; } for several lists at once.
  assign =
    pairs:
    lib.mkMerge (
      map (p: lib.genAttrs p.types (_: lib.mkDefault p.app)) pairs
    );

  sonic = config.sonic.desktop.enable;
  kde = pkgs.kdePackages;
in
{
  config = lib.mkMerge [
    (lib.mkIf config.ocimum.desktop.enable {
      xdg.mime.defaultApplications = assign [
        { types = pdf; app = "xreader.desktop"; }
        { types = images; app = "xviewer.desktop"; }
        { types = raw; app = "pix.desktop"; }
        { types = audio ++ video; app = "io.github.celluloid_player.Celluloid.desktop"; }
        { types = archives; app = "org.gnome.FileRoller.desktop"; }
      ];
    })

    (lib.mkIf sonic {
      environment.systemPackages = [
        kde.okular
        kde.gwenview
        kde.ark
        kde.elisa
        pkgs.celluloid
      ];
      xdg.mime.defaultApplications = assign [
        { types = pdf; app = "okularApplication_pdf.desktop"; }
        { types = images ++ raw; app = "org.kde.gwenview.desktop"; }
        { types = audio; app = "org.kde.elisa.desktop"; }
        { types = video; app = "io.github.celluloid_player.Celluloid.desktop"; }
        { types = archives; app = "org.kde.ark.desktop"; }
      ];
    })

    (lib.mkIf config.tulsi.dwm.enable {
      environment.systemPackages = [
        pkgs.zathura
        pkgs.xviewer
        pkgs.mpv
        pkgs.xarchiver
      ];
      xdg.mime.defaultApplications = assign [
        { types = pdf; app = "org.pwmt.zathura.desktop"; }
        { types = images ++ raw; app = "xviewer.desktop"; }
        { types = audio ++ video; app = "mpv.desktop"; }
        { types = archives; app = "xarchiver.desktop"; }
      ];
    })
  ];
}
