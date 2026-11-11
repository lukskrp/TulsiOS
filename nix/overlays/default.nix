{ gtk3-o-src, nixpkgs-src }:
final: prev: {
  tulsi-tools = final.callPackage ../packages/tulsi-tools.nix { };
  tulsi-package-index = final.callPackage ../packages/package-index.nix { nixpkgsSrc = nixpkgs-src; };
  gtk3-o = final.callPackage ../packages/gtk3-o.nix { src = gtk3-o-src; };
  ocimum-software-center = final.callPackage ../packages/ocimum-software-center.nix { };
}
