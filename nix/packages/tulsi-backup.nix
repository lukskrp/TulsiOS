# Backup (ADR 0036): the app and CLIs, which mirror home to a USB drive with
# a manifest (files plus the software list) and merge it back.
{
  lib,
  python3Packages,
  wrapGAppsHook3,
  gobject-introspection,
  gtk3,
  rsync,
}:

let
  root = ../../apps/tulsi-backup;
in
python3Packages.buildPythonApplication {
  pname = "tulsi-backup";
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

  nativeCheckInputs = [
    python3Packages.pytestCheckHook
    # The tests fake rsync's calls, but availability is still probed.
    rsync
  ];
  pythonImportsCheck = [
    "tulsi_backup.system"
    "tulsi_backup.cli"
    "tulsi_backup.app"
  ];

  dontWrapGApps = true;
  preFixup = ''
    makeWrapperArgs+=(
      "''${gappsWrapperArgs[@]}"
      --prefix PATH : "${lib.makeBinPath [ rsync ]}"
    )
  '';

  postInstall = ''
    install -Dm644 data/org.tulsi.Backup.desktop -t $out/share/applications
    install -Dm644 data/org.tulsi.Backup.svg -t $out/share/icons/hicolor/scalable/apps
  '';

  meta = {
    description = "Backup: your files and software list, to a USB drive and back";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "tulsi-backup";
  };
}
