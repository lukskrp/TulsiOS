# The ISO's reference installs (see nix/lib/reference-system.nix): one per
# desktop, and between them both boot loaders. Shared by the ISO and
# checks.install-iso-references, which installs with exactly these.
{
  self,
  testing ? false,
}:
map (r: import ../../lib/reference-system.nix ({ inherit self testing; } // r)) [
  {
    desktop = "ocimum";
    boot = "uefi";
  }
  {
    desktop = "dwm";
    boot = "bios";
  }
]
