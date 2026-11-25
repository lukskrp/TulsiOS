# Which program comes from which package, for tulsid's `Match` (ADR 0018): someone
# who types `apt install rg`, or downloads a .deb with /usr/bin/cvlc inside, is
# offered the package that has that program.
#
# Made from nix-index-database's small database (the programs in `bin/` of the
# packages Hydra builds for nixos-unstable), which tulsipkgs follows closely;
# tulsid drops attributes its package index does not have. Built once, offline
# at runtime.
#
# Format: `program<TAB>attr` lines, sorted.
{
  lib,
  stdenv,
  runCommand,
  fetchurl,
  nix-index,
  gawk,
}:

let
  release = "2026-11-22-102233";
  hashes = {
    x86_64-linux = "sha256-CDngn1SozPgiBl0zy1fxPXCeQeT/Eopc0TGRYmJu9/w=";
    aarch64-linux = "sha256-gNxMK5xd2gncM2aSLxkU0zzYv2Oz+12JB6v5ruyEmE0=";
  };
  system = stdenv.hostPlatform.system;
  database = fetchurl {
    url = "https://github.com/nix-community/nix-index-database/releases/download/${release}/index-${system}-small";
    hash = hashes.${system} or (throw "tulsi-program-index: no nix-index database for ${system}");
  };
in
runCommand "tulsi-program-index"
  {
    nativeBuildInputs = [
      nix-index
      gawk
    ];
    meta.description = "Programs and the TulsiOS packages that provide them";
    passthru = { inherit database release; };
  }
  ''
    mkdir db
    cp ${database} db/files
    # Packages people install (not parenthesised dependencies), files directly in bin/.
    nix-locate --db db --color never --regex '/bin/[^/]+$' \
      | awk '
          $1 ~ /^\(/ { next }
          {
            path = $NF
            if (path !~ /^\/nix\/store\/[^\/]+\/bin\/[^\/]+$/) next
            n = split(path, parts, "/"); program = parts[n]
            if (program ~ /^\./) next
            attr = $1
            sub(/\.(out|bin|dev|lib|man|doc|info|devdoc|debug|static|py|python|tools|cli)$/, "", attr)
            print program "\t" attr
          }' \
      | LC_ALL=C sort -u > $out
    echo "indexed $(wc -l < $out) programs"
    test -s $out
  ''
