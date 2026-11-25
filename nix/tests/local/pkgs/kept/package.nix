{
  lib,
  stdenvNoCC,
  requireFile,
}:
stdenvNoCC.mkDerivation {
  pname = "kept";
  version = "1.0";
  # A downloaded file, kept as part of the system (state.json keepSources, ADR 0018).
  src = requireFile {
    name = "kept-1.0-kept.tar.gz";
    hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
    message = "Added to the Nix store by TulsiOS (tulsi-adopt).";
    meta.license = lib.licenses.free;
  };
  installPhase = "mkdir $out";
  meta.description = "Built from a kept download";
}
