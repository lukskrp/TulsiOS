# All TulsiOS NixOS modules. Packages are referenced via `pkgs.callPackage`
# (not an overlay) so the modules also work with a read-only `pkgs`, e.g. in
# NixOS tests. Use `overlays.default` from the flake to add them to pkgs.
{ ... }:
{
  imports = [
    ./tulsi-state.nix
    ./tulsid.nix
    ./browser-extensions.nix
    ./software-center.nix
    ./assistant.nix
    ./ocimum-desktop.nix
    ./ocimum-greeter.nix
    ./gtk3-o.nix
    ./cache.nix
    ./kernel.nix
  ];
}
