# tulsi-file-tools: the file manager's quick actions (ADR 0037): resize and convert
# images, images to a PDF, audio/video to MP3, documents to PDF, plus the Nemo
# actions and KDE service menus for them, "Explain with Assistant" and "Send via
# LocalSend". Each conversion makes a new file beside the original.
{
  lib,
  python3Packages,
  wrapGAppsHook3,
  gobject-introspection,
  gtk3,
  imagemagick,
  ffmpeg,
}:

let
  root = ../../apps/tulsi-file-tools;
in
python3Packages.buildPythonApplication {
  pname = "tulsi-file-tools";
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
  pythonImportsCheck = [ "tulsi_file_tools.tools" ];

  dontWrapGApps = true;
  preFixup = ''
    makeWrapperArgs+=("''${gappsWrapperArgs[@]}")
    # LibreOffice (doc-to-pdf) is found on the system when it is installed.
    makeWrapperArgs+=(--suffix PATH : "${lib.makeBinPath [ imagemagick ffmpeg ]}")
  '';

  postInstall = ''
    install -Dm644 data/*.nemo_action -t $out/share/nemo/actions
    install -Dm644 data/*.desktop -t $out/share/kio/servicemenus
  '';

  meta = {
    description = "Quick file conversions for the file manager's right-click menu";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "tulsi-file-tools";
  };
}
