"""tulsi-install-system: installs TulsiOS onto a mounted root (ADR 0016).

Calamares (on the live ISO) and the VM tests both call it: they collect the
answers, this writes the system flake into <root>/etc/nixos and runs nixos-install.
"""
