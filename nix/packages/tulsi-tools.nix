{ lib, rustPlatform }:

let
  root = ../..;
in
rustPlatform.buildRustPackage {
  pname = "tulsi-tools";
  version = "0.0.1";

  src = lib.fileset.toSource {
    inherit root;
    fileset = lib.fileset.unions [
      (root + "/Cargo.toml")
      (root + "/Cargo.lock")
      (root + "/crates")
      (root + "/state")
    ];
  };

  cargoLock.lockFile = root + "/Cargo.lock";

  meta = {
    description = "TulsiOS command-line tools, daemon and MCP server";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "tulsi";
  };
}
