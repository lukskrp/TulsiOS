{ lib, rustPlatform }:

let
  root = ../..;
in
rustPlatform.buildRustPackage {
  pname = "tulsi-tools";
  version = "0.1.0";

  src = lib.fileset.toSource {
    inherit root;
    fileset = lib.fileset.unions [
      (root + "/Cargo.toml")
      (root + "/Cargo.lock")
      (root + "/crates")
      (root + "/state")
      (root + "/data")
    ];
  };

  cargoLock.lockFile = root + "/Cargo.lock";

  postInstall = ''
    install -Dm444 data/dbus/org.tulsi.Manager1.conf -t $out/share/dbus-1/system.d
    install -Dm444 data/polkit/org.tulsi.policy -t $out/share/polkit-1/actions
  '';

  meta = {
    description = "TulsiOS command-line tool, system daemon and MCP server";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "tulsi";
  };
}
