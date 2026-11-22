# The TulsiOS live ISO (ADR 0016): the live session of ./live.nix, and everything
# installing needs, so it works without a network.
#   nix build .#iso        -> result/iso/tulsios-<version>-x86_64-linux.iso
# The ISO is hybrid: written to a USB stick with dd (or Etcher) it boots on BIOS
# and UEFI machines alike, so it is also the "dd image".
{ self }:
{
  lib,
  pkgs,
  modulesPath,
  ...
}:

let
  version = lib.fileContents ../../../VERSION;

  # One reference install per desktop, between them both boot loaders: what an
  # install builds on top of is already in the ISO's store.
  references = import ./references.nix { inherit self; };

  # Artwork from Ocimum Desktop's sources (not its build).
  art = "${pkgs.cinnamon.src}/files/usr/share";
  wallpaper = "${art}/backgrounds/ocimum/tulsios-leaf.png";
  image =
    name: size: src:
    pkgs.runCommand name { nativeBuildInputs = [ pkgs.imagemagick ]; } ''
      magick ${src} -resize ${size}^ -gravity center -extent ${size} -strip PNG24:$out
    '';
in
{
  imports = [
    # Not installation-cd-graphical-calamares.nix: that one adds upstream Calamares
    # (NixOS settings) next to TulsiOS's, which tulsi.installer.calamares provides.
    (modulesPath + "/installer/cd-dvd/installation-cd-graphical-base.nix")
    ./live.nix
  ];

  nixpkgs.hostPlatform = "x86_64-linux";

  image.baseName = lib.mkForce "tulsios-${version}-${pkgs.stdenv.hostPlatform.system}";
  isoImage = {
    volumeID = "TULSIOS_${lib.replaceStrings [ "." ] [ "_" ] version}";
    appendToMenuLabel = " Live";
    splashImage = image "tulsios-syslinux.png" "640x480" wallpaper;
    # Unused while the theme is set (GRUB's fallback without one).
    efiSplashImage = image "tulsios-grub.png" "1920x1080" wallpaper;
    # The UEFI boot menu: the wallpaper cropped to the screen, not stretched.
    grubTheme = pkgs.callPackage ../../packages/tulsios-grub-theme.nix { };
  };

  # No boot splash: between the boot menu and the desktop the ISO shows boot
  # messages. Plymouth (on from installation-cd-graphical-base) races the graphics
  # driver taking over from the firmware's framebuffer under UEFI: it ends up in a
  # blocking keyboard read, stops forwarding the console it redirected, and boot
  # stalls behind systemd's next status line (about 1 boot in 5 in checks.iso-boot).
  boot.plymouth.enable = lib.mkForce false;

  # TulsiOS's kernel (7.3) has no ZFS module, which installer media switch on.
  boot.supportedFilesystems.zfs = lib.mkForce false;

  tulsi.installer = {
    offlineSystems = map (r: r.config.system.build.toplevel) references;
    buildDependencies =
      import ../../lib/install-closure.nix pkgs
      ++ lib.concatMap (import ../../lib/offline-rebuild-inputs.nix) references;
  };
}
