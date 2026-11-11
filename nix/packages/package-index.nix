# Package search index for tulsid, generated from the pinned nixpkgs the same
# way nixpkgs builds search.nixos.org's packages.json (packages-info.nix).
# Built once on the build host and cached; no evaluation happens at runtime.
#
# Format: JSON array of [attr, pname, version, description, unfree], sorted by attr.
{
  runCommand,
  nix,
  jq,
  nixpkgsSrc,
}:

runCommand "tulsi-package-index"
  {
    nativeBuildInputs = [
      nix
      jq
    ];
  }
  ''
    export NIX_STATE_DIR=$TMPDIR NIX_PATH= HOME=$TMPDIR
    nix-instantiate --eval --raw \
      --option experimental-features "" \
      --expr "import ${nixpkgsSrc}/pkgs/top-level/packages-info.nix {}" \
      | jq -c '
          .packages
          | to_entries
          | map(select(.value.meta.broken != true)
                | [ .key,
                    .value.pname,
                    .value.version,
                    ((.value.meta.description // "") | gsub("\\s+"; " ")),
                    (.value.meta.unfree == true) ])
          | sort_by(.[0])
        ' > $out
    echo "indexed $(jq length $out) packages"
  ''
