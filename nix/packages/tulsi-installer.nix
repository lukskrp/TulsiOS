# tulsi-install-system: installs TulsiOS onto a mounted root (ADR 0016).
# `source` is the TulsiOS flake the new system is built from (the flake's
# self.outPath); nix/modules/installer.nix passes it.
{
  lib,
  python3Packages,
  makeWrapper,
  nix,
  nixos-install-tools,
  source ? null,
}:

let
  root = ../../apps/tulsi-installer;
  template = ../../data/system-flake.nix.in;
  initialState = ../../state/initial.json;
in
python3Packages.buildPythonApplication {
  pname = "tulsi-installer";
  version = "0.1.0";
  pyproject = true;

  src = lib.fileset.toSource {
    inherit root;
    fileset = lib.fileset.difference root (lib.fileset.fileFilter (f: f.hasExt "pyc") root);
  };

  build-system = [ python3Packages.setuptools ];
  nativeBuildInputs = [ makeWrapper ];

  # nix-instantiate --parse checks that what the installer writes is valid Nix.
  nativeCheckInputs = [
    python3Packages.pytestCheckHook
    nix
  ];
  preCheck = ''
    export TULSI_FLAKE_TEMPLATE=${template}
  '';
  pythonImportsCheck = [
    "tulsi_installer.cli"
    "tulsi_installer.calamares"
  ];

  makeWrapperArgs = [
    "--prefix"
    "PATH"
    ":"
    (lib.makeBinPath [
      nix
      nixos-install-tools
    ])
    "--set-default"
    "TULSI_FLAKE_TEMPLATE"
    "${template}"
    "--set-default"
    "TULSI_INITIAL_STATE"
    "${initialState}"
    "--set-default"
    "TULSI_STATE_VERSION"
    lib.trivial.release
  ]
  ++ lib.optionals (source != null) [
    "--set-default"
    "TULSI_SOURCE"
    "${source}"
  ];

  meta = {
    description = "Installs TulsiOS onto a mounted root: writes the system flake, runs nixos-install";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "tulsi-install-system";
  };
}
