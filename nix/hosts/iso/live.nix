# The live session of the TulsiOS ISO (ADR 0016): Ocimum Desktop, logged in as
# `nixos`, with Calamares started at login. Kept apart from the ISO image itself
# (default.nix) so checks.live-session can test it in an ordinary VM, without
# building an ISO.
{ lib, ... }:
{
  tulsi.desktop = {
    session = "ocimum";
    autoLoginUser = "nixos";
  };
  system.nixos.variantName = "Live";

  # The live user has no password: never lock the screen or suspend.
  services.xserver.desktopManager.cinnamon.extraGSettingsOverrides = ''
    [org.cinnamon.desktop.screensaver]
    lock-enabled=false

    [org.cinnamon.desktop.session]
    idle-delay=uint32 0

    [org.cinnamon.settings-daemon.plugins.power]
    sleep-inactive-ac-timeout=0
    sleep-inactive-battery-timeout=0
  '';

  # Nothing to set up or undo on a system that lives in RAM: no first-login
  # Starah setup, no adopt hints (tulsid, the Software Center and the Assistant
  # stay off, as they are by default).
  services.starah.enable = false;
  tulsi.adopt.enable = false;

  # Calamares, started at login through pkexec (it runs as root).
  tulsi.installer = {
    enable = true;
    calamares.enable = true;
  };
}
