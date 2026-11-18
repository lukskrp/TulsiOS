# TulsiOS's own tools and apps. Forked upstream software (Ocimum Desktop,
# GTK3-O) lives in tulsipkgs, the nixpkgs fork this flake builds on.
{ nixpkgs-src }:
final: prev: {
  tulsi-tools = final.callPackage ../packages/tulsi-tools.nix { };
  tulsi-package-index = final.callPackage ../packages/package-index.nix { nixpkgsSrc = nixpkgs-src; };
  ocimum-software-center = final.callPackage ../packages/ocimum-software-center.nix { };
  ocimum-assistant = final.callPackage ../packages/ocimum-assistant.nix { };
  ocimum-greeter = final.callPackage ../packages/ocimum-greeter.nix { };
  tulsi-installer = final.callPackage ../packages/tulsi-installer.nix { };
  calamares-tulsios-extensions = final.callPackage ../packages/calamares-tulsios-extensions.nix { };
}
