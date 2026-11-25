# The Nix Editor's guide (ADR 0019): every example parses; the packaging examples
# pass TulsiOS's rules for local packages; every link leads somewhere.
{
  callPackage,
  runCommand,
  python3,
  nix,
}:

let
  tools = callPackage ../packages/tulsi-tools.nix { };
in
runCommand "nix-guide-check" { nativeBuildInputs = [ python3 nix ]; } ''
  export HOME=$TMPDIR NIX_STATE_DIR=$TMPDIR/state NIX_LOG_DIR=$TMPDIR/log
  python3 -I ${./nix-guide-check.py} ${../../apps/ocimum-nix-editor} ${tools}/bin/tulsi
  touch $out
''
