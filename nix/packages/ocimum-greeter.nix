# Ocimum Greeter: TulsiOS's login screen for greetd (Python + PyGObject on OTK).
# Run by nix/modules/ocimum-greeter.nix inside an XLibre server of its own.
{
  lib,
  python3Packages,
  wrapGAppsHook3,
  gobject-introspection,
  otk,
  librsvg,
}:

let
  root = ../../apps/ocimum-greeter;
in
python3Packages.buildPythonApplication {
  pname = "ocimum-greeter";
  version = "0.1.0";
  pyproject = true;

  src = lib.fileset.toSource {
    inherit root;
    fileset = lib.fileset.difference root (lib.fileset.fileFilter (f: f.hasExt "pyc") root);
  };

  build-system = [ python3Packages.setuptools ];

  nativeBuildInputs = [
    wrapGAppsHook3
    gobject-introspection
  ];
  buildInputs = [
    otk # Otk-3.0 / Odk-3.0 typelibs (otk propagates graphene for Osk-3.0)
    librsvg # the SVG wallpaper, through gdk-pixbuf
  ];
  dependencies = with python3Packages; [ pygobject3 ];

  nativeCheckInputs = [ python3Packages.pytestCheckHook ];
  pythonImportsCheck = [
    "ocimum_greeter.greetd"
    "ocimum_greeter.login"
    "ocimum_greeter.sessions"
  ];

  dontWrapGApps = true;
  preFixup = ''
    makeWrapperArgs+=("''${gappsWrapperArgs[@]}")
  '';

  meta = {
    description = "TulsiOS's login screen: a greeter for greetd, written with OTK";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "ocimum-greeter";
  };
}
