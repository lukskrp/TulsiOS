# Ocimum Software Center (Python + PyGObject, GTK 3). Built against stock
# gtk3; on TulsiOS the system-wide graft (ocimum.gtk3o) makes it use GTK3-O.
{
  lib,
  python3Packages,
  wrapGAppsHook3,
  gobject-introspection,
  gtk3,
}:

let
  root = ../../apps/ocimum-software-center;
in
python3Packages.buildPythonApplication {
  pname = "ocimum-software-center";
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
  pythonImportsCheck = [ "ocimum_software_center.model" ];

  # Wrap once: python's wrapper plus the GApps environment.
  dontWrapGApps = true;
  preFixup = ''
    makeWrapperArgs+=("''${gappsWrapperArgs[@]}")
  '';

  postInstall = ''
    install -Dm644 data/org.tulsi.SoftwareCenter.desktop -t $out/share/applications
  '';

  meta = {
    description = "Install and remove software on TulsiOS without writing Nix";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "ocimum-software-center";
  };
}
