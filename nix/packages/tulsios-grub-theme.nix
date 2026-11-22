# TulsiOS's GRUB theme: NixOS's (its fonts, menu frame and countdown bar) with the
# Tulsi Leaf wallpaper, cropped to fill the screen whatever its shape instead of
# stretched, and the TulsiOS logo above the menu. Used by the live ISO's UEFI boot
# menu and by installed systems that boot with GRUB (BIOS).
{
  runCommand,
  imagemagick,
  librsvg,
  nixos-grub2-theme,
  cinnamon,
}:

let
  # Artwork from Ocimum Desktop's sources (not its build).
  art = "${cinnamon.src}/files/usr/share";
in
runCommand "tulsios-grub-theme"
  {
    nativeBuildInputs = [
      imagemagick
      librsvg
    ];
  }
  ''
    cp -r ${nixos-grub2-theme} $out
    chmod -R u+w $out

    # GRUB reads plain 8-bit RGB PNGs.
    magick ${art}/backgrounds/ocimum/tulsios-leaf.png -strip PNG24:$out/background.png
    # The white logo reads on the dark green wallpaper.
    rsvg-convert -w 100 -h 100 ${art}/icons/hicolor/scalable/apps/tulsi-start-white.svg -o $out/logo.png

    substituteInPlace $out/theme.txt \
      --replace-fail 'width = 319' 'width = 100' \
      --replace-fail 'left = 50%-160 # (image width) / 2 = 160' 'left = 50%-50 # (image width) / 2' \
      --replace-fail 'desktop-image: "background.png"' \
        'desktop-image: "background.png"
    # Fill the screen without distorting the wallpaper (GRUB 2.12+): crop what does not fit.
    desktop-image-scale-method: "crop"
    desktop-image-h-align: "center"
    desktop-image-v-align: "center"'
  ''
