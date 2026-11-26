# Update Manager (ADR 0034): the app and `tulsi-update-manager`, which checks
# for TulsiOS releases, upgrades through tulsid, and lists older system
# versions and /home snapshots.
{
  lib,
  python3Packages,
  wrapGAppsHook3,
  gobject-introspection,
  gtk3,
}:

let
  root = ../../apps/tulsi-update-manager;
in
python3Packages.buildPythonApplication {
  pname = "tulsi-update-manager";
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
    "tulsi_update_manager.system"
    "tulsi_update_manager.app"
  ];

  dontWrapGApps = true;
  preFixup = ''
    makeWrapperArgs+=("''${gappsWrapperArgs[@]}")
  '';

  postInstall = ''
    install -Dm644 data/org.tulsi.UpdateManager.desktop -t $out/share/applications
    install -Dm644 data/org.tulsi.UpdateManager.svg -t $out/share/icons/hicolor/scalable/apps
  '';

  meta = {
    description = "Update Manager: TulsiOS releases, older versions, and home snapshots";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "tulsi-update-manager";
  };
}
