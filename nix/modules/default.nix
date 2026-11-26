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
    ./nix-editor.nix
    ./themes.nix
    ./agent-skills.nix
    ./assistant.nix
    ./ocimum-desktop.nix
    ./sonic-desktop.nix
    ./ocimum-greeter.nix
    ./desktop.nix
    ./dwm.nix
    ./installer.nix
    ./gtk3-o.nix
    ./cache.nix
    ./adopt.nix
    ./kernel.nix
    ./branding.nix
    ./cleanup.nix
    ./agent-gating.nix
    ./home-snapshots.nix
    ./drivers.nix
    ./editor.nix
    ./printing-scanning.nix
    ./updater.nix
    ./utilities.nix
    ./codecs.nix
    ./default-apps.nix
    ./file-actions.nix
  ];
}
