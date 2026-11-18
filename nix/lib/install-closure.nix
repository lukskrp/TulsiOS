# What nixos-install needs to build the per-machine parts of a TulsiOS system
# (hostname, users, disks, initrd, boot loader) without a network, next to the
# closures of reference installs (tulsi.installer.offlineSystems). Adapted from
# nixpkgs' nixos/tests/installer.nix; used by the install tests and the ISO.
pkgs: with pkgs; [
  stdenv
  stdenvNoCC
  bintools
  brotli
  brotli.dev
  brotli.lib
  desktop-file-utils
  docbook5
  docbook_xsl_ns
  kbd.dev
  kmod.dev
  libarchive.dev
  libcap-text-verifier
  libxml2.bin
  libxslt.bin
  nixos-rebuild-ng
  perlPackages.ConfigIniFiles
  perlPackages.FileSlurp
  perlPackages.JSON
  perlPackages.ListCompare
  perlPackages.XMLLibXML
  (python3.withPackages (p: [ p.mistune ]))
  shared-mime-info
  sudo
  switch-to-configuration-ng
  texinfo
  unionfs-fuse
  lndir
  shellcheck-minimal
  systemd.out
  curl
  # initrd and systemd-boot
  makeInitrdNGTool
  zstd
  zstd.bin
  mypy
  # GRUB (BIOS installs)
  grub2
  grub2_efi
  perlPackages.FileCopyRecursive
  perlPackages.XMLSAX
  perlPackages.XMLSAXBase
]
