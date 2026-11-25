# Drivers (ADR 0029): the app and `tulsi-drivers`, which detect the GPUs, Wi-Fi
# and processor and choose their drivers as a `tulsi config` edit that takes
# effect at the next restart and goes back by itself unless it is kept.
{
  lib,
  python3Packages,
  wrapGAppsHook3,
  gobject-introspection,
  gtk3,
  hwdata,
}:

let
  root = ../../apps/tulsi-drivers;
in
python3Packages.buildPythonApplication {
  pname = "tulsi-drivers";
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
  buildInputs = [ gtk3 ];
  dependencies = [ python3Packages.pygobject3 ];

  nativeCheckInputs = [ python3Packages.pytestCheckHook ];
  pythonImportsCheck = [
    "tulsi_drivers.catalogue"
    "tulsi_drivers.cli"
    "tulsi_drivers.app"
  ];

  dontWrapGApps = true;
  preFixup = ''
    makeWrapperArgs+=(
      "''${gappsWrapperArgs[@]}"
      --set-default TULSI_PCI_IDS ${hwdata}/share/hwdata/pci.ids
    )
  '';

  postInstall = ''
    install -Dm644 data/org.tulsi.Drivers.desktop -t $out/share/applications
    install -Dm644 data/tulsi-drivers-trial.desktop $out/etc/xdg/autostart/tulsi-drivers-trial.desktop
    install -Dm644 data/org.tulsi.Drivers.svg -t $out/share/icons/hicolor/scalable/apps
  '';

  meta = {
    description = "Drivers for the GPUs, Wi-Fi and processor of a TulsiOS computer";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "tulsi-drivers";
  };
}
