# Calamares settings, branding and the `tulsios` job for the TulsiOS installer
# (ADR 0016). Upstream calamares-nixos-extensions' module settings (locale,
# keyboard, users, partition, mount, finished) are reused as they are; TulsiOS
# replaces the sequence, the desktop page, the welcome checks, the branding and
# the install job. Use with calamares-nixos.override { calamares-nixos-extensions = …; }.
{
  lib,
  stdenvNoCC,
  calamares-nixos-extensions,
  cinnamon,
  python3,
  librsvg,
  version ? lib.fileContents ../../VERSION,
}:

let
  root = ../../installer/calamares;
in
stdenvNoCC.mkDerivation {
  pname = "calamares-tulsios-extensions";
  inherit version;

  src = lib.fileset.toSource {
    inherit root;
    fileset = root;
  };

  nativeBuildInputs = [
    python3
    librsvg
  ];

  installPhase = ''
    runHook preInstall
    mkdir -p $out/etc/calamares/modules $out/lib/calamares/modules $out/share/calamares/branding

    # Upstream's module settings (locale.conf already points at glibcLocales).
    up=${calamares-nixos-extensions}
    for conf in locale keyboard users partition mount finished; do
      install -m644 $up/etc/calamares/modules/$conf.conf $out/etc/calamares/modules/
    done
    install -m644 config/modules/*.conf $out/etc/calamares/modules/
    substitute config/settings.conf $out/etc/calamares/settings.conf --replace-fail @out@ $out

    cp -r modules/tulsios modules/tulsios-online $out/lib/calamares/modules/
    python3 -m py_compile modules/tulsios/main.py modules/tulsios-online/main.py

    cp -r branding/tulsios $out/share/calamares/branding/
    chmod -R u+w $out/share/calamares/branding
    substituteInPlace $out/share/calamares/branding/tulsios/branding.desc --replace-fail @version@ ${version}
    # The TulsiOS logo from Ocimum Desktop's sources (not its build): the vector
    # for the slideshow, and a 512 px PNG for the branding images, which Calamares
    # would otherwise rasterise at the SVG's own small size and then scale up.
    icons=${cinnamon.src}/files/usr/share/icons/hicolor/scalable/apps
    if [ -e $icons/tulsi-start.svg ]; then logo=$icons/tulsi-start.svg; else logo=$icons/ocimum.svg; fi
    install -m644 $logo $out/share/calamares/branding/tulsios/logo.svg
    rsvg-convert -w 512 -h 512 $logo -o $out/share/calamares/branding/tulsios/logo.png
    runHook postInstall
  '';

  meta = {
    description = "Calamares settings, branding and install job for TulsiOS";
    license = with lib.licenses; [ mit ];
    platforms = lib.platforms.linux;
  };
}
