# File History and the TulsiOS Welcome window (ADR 0027): earlier versions of
# files from /home's snapshots, and the first-login window that offers them.
{
  lib,
  python3Packages,
  wrapGAppsHook3,
  gobject-introspection,
  gtk3,
  glib,
  trash-cli,
  snapper,
  xdg-utils,
}:

let
  root = ../../apps/ocimum-file-history;
in
python3Packages.buildPythonApplication {
  pname = "ocimum-file-history";
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
    "ocimum_file_history.history"
    "ocimum_file_history.welcome"
  ];

  dontWrapGApps = true;
  preFixup = ''
    makeWrapperArgs+=(
      "''${gappsWrapperArgs[@]}"
      --suffix PATH : ${
        lib.makeBinPath [
          glib # gio trash
          trash-cli
          snapper
          xdg-utils
        ]
      }
    )
  '';

  postInstall = ''
    install -Dm644 data/org.tulsi.FileHistory.desktop data/org.tulsi.Welcome.desktop -t $out/share/applications
    install -Dm644 data/tulsi-welcome-autostart.desktop $out/etc/xdg/autostart/tulsi-welcome.desktop
    install -Dm644 data/file-history.nemo_action -t $out/share/nemo/actions
    install -Dm644 data/file-history-servicemenu.desktop $out/share/kio/servicemenus/tulsi-file-history.desktop
  '';

  meta = {
    description = "File History and the TulsiOS Welcome window";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "ocimum-file-history";
  };
}
