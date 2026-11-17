{ stdenvNoCC }:
stdenvNoCC.mkDerivation {
  pname = "frob";
  version = "1.0";
  dontUnpack = true;
  installPhase = ''
    mkdir -p $out/bin
    printf '#!/bin/sh\necho "frob 1.0"\n' > $out/bin/frob
    chmod +x $out/bin/frob
  '';
  meta.description = "Frobnicates things";
}
