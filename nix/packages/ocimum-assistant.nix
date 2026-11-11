# Ocimum Assistant (Python + PyGObject, GTK 3; Claude via the anthropic SDK).
{
  lib,
  python3Packages,
  wrapGAppsHook3,
  gobject-introspection,
  gtk3,
  libsecret,
}:

let
  root = ../../apps/ocimum-assistant;
in
python3Packages.buildPythonApplication {
  pname = "ocimum-assistant";
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
    libsecret
  ];
  dependencies = with python3Packages; [
    pygobject3
    anthropic
  ];

  nativeCheckInputs = [ python3Packages.pytestCheckHook ];
  pythonImportsCheck = [
    "ocimum_assistant.agent"
    "ocimum_assistant.providers"
  ];

  dontWrapGApps = true;
  preFixup = ''
    makeWrapperArgs+=("''${gappsWrapperArgs[@]}")
  '';

  postInstall = ''
    install -Dm644 data/org.tulsi.Assistant.desktop -t $out/share/applications
  '';

  meta = {
    description = "Change TulsiOS in plain language; every change is approved by you first";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "ocimum-assistant";
  };
}
