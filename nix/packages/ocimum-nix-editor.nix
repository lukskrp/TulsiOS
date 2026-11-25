# Nix Editor (ADR 0019): Python + PyGObject, GTK 3 and GtkSourceView 4, with nixd for
# suggestions and problem marks, and a Nix guide written for TulsiOS beside the file.
# On TulsiOS the system-wide graft (ocimum.gtk3o) makes it use GTK3-O.
{
  lib,
  python3Packages,
  wrapGAppsHook3,
  gobject-introspection,
  gtk3,
  gtksourceview4,
  nixd,
}:

let
  root = ../../apps/ocimum-nix-editor;
in
python3Packages.buildPythonApplication {
  pname = "ocimum-nix-editor";
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
    gtksourceview4
  ];
  dependencies = [ python3Packages.pygobject3 ];

  nativeCheckInputs = [ python3Packages.pytestCheckHook ];
  pythonImportsCheck = [
    "ocimum_nix_editor.guide"
    "ocimum_nix_editor.lsp"
  ];

  # Wrap once: python's wrapper plus the GApps environment; nixd is the editor's own.
  dontWrapGApps = true;
  preFixup = ''
    makeWrapperArgs+=("''${gappsWrapperArgs[@]}" --set-default NIX_EDITOR_NIXD ${lib.getExe nixd})
  '';

  postInstall = ''
    install -Dm644 data/org.tulsi.NixEditor.desktop -t $out/share/applications
    install -Dm644 data/org.tulsi.NixEditor.xml -t $out/share/mime/packages
    install -Dm644 data/org.tulsi.NixEditor.svg -t $out/share/icons/hicolor/scalable/apps
  '';

  meta = {
    description = "Write and fix Nix packages, with suggestions and a Nix guide beside the file";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "ocimum-nix-editor";
  };
}
