# tulsistick (ADR 0037): TulsiOS USB Stick Writer and Formatter, from its own
# repository (github:lukskrp/tulsistick). Writes ISOs with verification and
# formats sticks for carrying files; only removable USB drives are listed.
{
  lib,
  python3Packages,
  wrapGAppsHook3,
  gobject-introspection,
  gtk3,
  fetchFromGitHub,
  util-linux,
  parted,
  dosfstools,
  exfatprogs,
  ntfs3g,
  e2fsprogs,
  coreutils,
}:

python3Packages.buildPythonApplication {
  pname = "tulsi-stick";
  version = "0.1.0";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "lukskrp";
    repo = "tulsistick";
    rev = "3f654263750923e70a82a1bad928816a00d50412";
    hash = "sha256-8EP5G5i/f2GQrm6SplUUqZIkNgOyhzsIFbOgTpaVg3k=";
  };

  build-system = [ python3Packages.setuptools ];
  nativeBuildInputs = [
    wrapGAppsHook3
    gobject-introspection
  ];
  buildInputs = [ gtk3 ];
  dependencies = [ python3Packages.pygobject3 ];

  nativeCheckInputs = [ python3Packages.pytestCheckHook ];
  pythonImportsCheck = [
    "tulsi_stick.system"
    "tulsi_stick.cli"
    "tulsi_stick.app"
  ];

  dontWrapGApps = true;
  preFixup = ''
    makeWrapperArgs+=(
      "''${gappsWrapperArgs[@]}"
      --prefix PATH : "${
        lib.makeBinPath [
          util-linux
          parted
          dosfstools
          exfatprogs
          ntfs3g
          e2fsprogs
          coreutils
        ]
      }"
    )
  '';

  postInstall = ''
    install -Dm644 data/org.tulsi.Stick.desktop -t $out/share/applications
    install -Dm644 data/org.tulsi.Stick.svg -t $out/share/icons/hicolor/scalable/apps
  '';

  meta = {
    description = "TulsiOS USB Stick Writer and Formatter";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "tulsi-stick";
  };
}
