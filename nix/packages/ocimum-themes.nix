# Themes (ADR 0021): tulsi-theme, which turns a palette (Omarchy's colors.toml)
# into each desktop's own theme at switch time, and the Themes app over it.
# Mint-Y's sources and libsass come along, since a switch compiles Mint-Y in the
# palette's colours, as Linux Mint builds its own colour variants.
{
  lib,
  python3Packages,
  wrapGAppsHook3,
  gobject-introspection,
  gtk3,
  gdk-pixbuf,
  librsvg,
  glib,
  dconf,
  git,
  xrdb,
  xwallpaper,
  mint-themes,
  cinnamon,
}:

let
  root = ../../apps/ocimum-themes;
  mintSrc = mint-themes.src;
  mintThemes = "${mint-themes}/share/themes";
  # Tulsi Leaf, for themes that bring no background of their own.
  leaf = "${cinnamon.src}/files/usr/share/backgrounds/ocimum/tulsios-leaf.png";
in
python3Packages.buildPythonApplication {
  pname = "ocimum-themes";
  version = "0.1.0";
  pyproject = true;

  src = lib.fileset.toSource {
    inherit root;
    fileset = root;
  };

  build-system = [ python3Packages.setuptools ];

  nativeBuildInputs = [
    wrapGAppsHook3
    gobject-introspection
  ];
  buildInputs = [
    gtk3
    gdk-pixbuf
    librsvg # the SVG pixbuf loader, for previews
  ];
  dependencies = with python3Packages; [
    pygobject3
    pycairo
    libsass
  ];

  nativeCheckInputs = [
    python3Packages.pytestCheckHook
    git
    librsvg
  ];
  # The Mint-Y compile tests run against the real sources.
  preCheck = ''
    export TULSI_THEME_MINT_SRC=${mintSrc} TULSI_THEME_MINT_THEMES=${mintThemes}
  '';
  pythonImportsCheck = [
    "tulsi_theme.cli"
    "tulsi_theme.mint"
  ];

  dontWrapGApps = true;
  preFixup = ''
    makeWrapperArgs+=(
      "''${gappsWrapperArgs[@]}"
      --set TULSI_THEME_MINT_SRC ${mintSrc}
      --set TULSI_THEME_MINT_THEMES ${mintThemes}
      --set TULSI_THEME_STOCK $out/share/tulsi/themes
      --set-default TULSI_THEME_RSVG ${lib.getExe' librsvg "rsvg-convert"}
      --set-default TULSI_THEME_DEFAULT_BACKGROUND ${leaf}
      --suffix PATH : ${
        lib.makeBinPath [
          glib # gsettings
          dconf
          git
          xrdb # dwm
          xwallpaper
        ]
      }
    )
  '';

  postInstall = ''
    mkdir -p $out/share/tulsi
    cp -r themes $out/share/tulsi/themes
    install -Dm644 THIRD_PARTY.md -t $out/share/doc/ocimum-themes
    install -Dm644 data/org.tulsi.Themes.desktop -t $out/share/applications
    install -Dm644 data/org.tulsi.Themes.svg -t $out/share/icons/hicolor/scalable/apps
  '';

  meta = {
    description = "The desktop's colours and background from palettes (Omarchy's colors.toml)";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "ocimum-themes";
  };
}
