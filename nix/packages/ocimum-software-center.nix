# Ocimum Software Center (Python + PyGObject, GTK 3). Built against stock
# gtk3; on TulsiOS the system-wide graft (ocimum.gtk3o) makes it use GTK3-O.
{
  lib,
  python3Packages,
  wrapGAppsHook3,
  gobject-introspection,
  gtk3,
  gettext,
}:

let
  root = ../../apps/ocimum-software-center;
  # TulsiOS' translations (po/<lang>.po), merged into the launchers at build time.
  po = lib.fileset.toSource {
    root = ../../po;
    fileset = lib.fileset.fileFilter (f: f.hasExt "po") ../../po;
  };
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
    gettext
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
    # The AI Agents shortcut (ADR 0023), with Name[xx]= etc. from each po/xx.po.
    # msgfmt reads the languages from LINGUAS: the .po files there are.
    mkdir -p po && cp -r ${po}/. po/ && chmod -R u+w po
    find po -maxdepth 1 -name '*.po' -printf '%f\n' | sed 's/\.po$//' | sort > po/LINGUAS
    if [ -s po/LINGUAS ]; then
      msgfmt --desktop --template=data/org.tulsi.AIAgents.desktop.in -d po \
        -o $out/share/applications/org.tulsi.AIAgents.desktop
    else
      install -Dm644 data/org.tulsi.AIAgents.desktop.in $out/share/applications/org.tulsi.AIAgents.desktop
    fi
    install -Dm644 data/org.tulsi.AIAgents.svg -t $out/share/icons/hicolor/scalable/apps
  '';

  meta = {
    description = "Install and remove software on TulsiOS without writing Nix";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "ocimum-software-center";
  };
}
