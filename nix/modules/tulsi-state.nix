# tulsi.state — the declarative contract between TulsiOS tools and NixOS.
#
# GUIs, the CLI and the agent never write Nix code; they edit a JSON state
# file (see state/schema.json). This module turns that file into NixOS config.
# The Nix store is never mutated directly: every change becomes a new system
# generation, so rollback is always available.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.tulsi.state;
  # Only read when enabled: `services` below takes its attribute names from the
  # file, and the module system needs those names even under mkIf false.
  state = if cfg.enable then lib.importJSON cfg.file else { };

  packageNames = state.packages or [ ];
  firefoxExtensions = state.browserExtensions.firefox or [ ];
  chromiumExtensions = state.browserExtensions.chromium or [ ];
  services = state.services or { };
  # Packages made on this machine: tulsi/pkgs/<name>/package.nix next to state.json.
  localPackages = state.localPackages or [ ];
  localPackageFile = name: dirOf cfg.file + "/pkgs/${name}/package.nix";
  # Licences a person accepted, limited to what tulsid allows (tulsi.daemon.unfreeAgents)
  # and to local packages.
  acceptedUnfree = lib.intersectLists (state.acceptedLicenses or [ ]) (
    (config.tulsi.daemon.unfreeAgents or [ ]) ++ localPackages
  );

  # "vlc" or "python3Packages.requests" -> derivation, with a readable error.
  resolvePackage =
    name:
    let
      path = lib.splitString "." name;
    in
    if builtins.elem name localPackages then
      pkgs.callPackage (localPackageFile name) { }
    else if lib.hasAttrByPath path pkgs then
      lib.getAttrFromPath path pkgs
    else
      throw "tulsi.state: unknown package '${name}' in ${toString cfg.file}";

  # AMO accepts the add-on GUID in its "latest" download URL.
  firefoxExtensionSettings = lib.listToAttrs (
    map (id: {
      name = id;
      value = {
        installation_mode = "force_installed";
        install_url = "https://addons.mozilla.org/firefox/downloads/latest/${id}/latest.xpi";
      };
    }) firefoxExtensions
  );
in
{
  options.tulsi.state = {
    enable = lib.mkEnableOption "the TulsiOS declarative state file";

    file = lib.mkOption {
      type = lib.types.path;
      example = lib.literalExpression "./tulsi/state.json";
      description = ''
        JSON file (schema: state/schema.json) holding user-chosen packages,
        browser extensions and service toggles. Managed by tulsid, the
        Software Center and the Ocimum Assistant.
      '';
    };
  };

  config = lib.mkIf cfg.enable (
    lib.mkMerge [
      { environment.systemPackages = map resolvePackage packageNames; }

      # Unfree agent CLIs whose licence was accepted in the Software Center.
      (lib.mkIf (acceptedUnfree != [ ]) {
        nixpkgs.config.allowUnfreePredicate = pkg: builtins.elem (lib.getName pkg) acceptedUnfree;
      })

      (lib.mkIf (firefoxExtensions != [ ]) {
        programs.firefox.enable = lib.mkDefault true;
        programs.firefox.policies.ExtensionSettings = firefoxExtensionSettings;
      })

      (lib.mkIf (chromiumExtensions != [ ]) {
        programs.chromium.enable = lib.mkDefault true;
        programs.chromium.extensions = chromiumExtensions;
      })

      # Phase 1: only `enable` is supported per service. Unknown service names
      # fail at evaluation time with the usual "option does not exist" error.
      { services = lib.mapAttrs (_: svc: { enable = svc.enable or false; }) services; }
    ]
  );
}
