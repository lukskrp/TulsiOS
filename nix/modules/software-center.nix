# ocimum.softwareCenter — GUI to install/uninstall software via tulsi.state (Phase 3).
{ config, lib, ... }:

{
  options.ocimum.softwareCenter.enable = lib.mkEnableOption "the Ocimum Software Center (Phase 3, not functional yet)";

  config = lib.mkIf config.ocimum.softwareCenter.enable {
    assertions = [
      {
        assertion = config.tulsi.daemon.enable;
        message = "ocimum.softwareCenter requires tulsi.daemon.enable = true.";
      }
    ];
    # TODO(phase-3): add the GTK4 application package and desktop entry.
  };
}
