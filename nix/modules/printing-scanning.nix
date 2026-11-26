# tulsi.printingScanning — printers and scanners that just work (Mint parity).
#
# Ocimum first, all desktops: CUPS with the common drivers, driverless
# discovery (Avahi/mDNS, cups-browsed, ipp-usb) and SANE with the AirScan
# backend, so USB and network printers/scanners mostly need no setup.
# Non-free firmware/drivers are pre-accepted here (Mint parity): this module
# sets `nixpkgs.config.allowUnfree`, which a person can override.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.tulsi.printingScanning;
  isOcimum = config.ocimum.desktop.enable;
  isSonic = config.sonic.desktop.enable;
  isDwm = config.tulsi.dwm.enable;
  # Unfree printer firmware Mint ships and TulsiOS pre-accepts (via
  # allowUnfree below): cnijfilter2, samsung-unified-linux-driver,
  # hplipWithPlugin/hplip-plugin, foomatic-db-ppds-withNonfreeDb.
in
{
  options.tulsi.printingScanning.enable = lib.mkOption {
    type = lib.types.bool;
    default = (isOcimum || isSonic || isDwm) && !config.tulsi.installer.enable;
    defaultText = lib.literalMD "on with any TulsiOS desktop, except the live installer";
    description = "Printers and scanners by default: CUPS drivers, Avahi discovery, SANE + AirScan, scanner app.";
  };

  config = lib.mkIf cfg.enable (
    lib.mkMerge [
      {
        # Mint parity is explicit: non-free printer firmware is pre-accepted.
        # Override with `nixpkgs.config.allowUnfree = lib.mkForce false;`
        # plus your own allowUnfreePredicate to harden again.
        nixpkgs.config.allowUnfree = lib.mkDefault true;

        services.printing = {
          enable = lib.mkDefault true;
          browsed.enable = lib.mkDefault true;
          drivers = with pkgs; [
            gutenprint
            gutenprintBin
            hplip
            splix
            brlaser
            cnijfilter2
          ];
        };

        # Driverless USB (IPP-over-USB/AirPrint/WSD) and network discovery.
        services.ipp-usb.enable = lib.mkDefault true;
        services.avahi = {
          enable = lib.mkDefault true;
          nssmdns4 = lib.mkDefault true;
          openFirewall = lib.mkDefault true;
        };

        # Scanning: SANE + AirScan (driverless network/USB), firewall open for
        # network scanners (saned/AirScan discovery via mDNS).
        hardware.sane = {
          enable = lib.mkDefault true;
          extraBackends = [ pkgs.sane-airscan ];
          openFirewall = lib.mkDefault true;
        };
      }

      # Ocimum (and dwm, which uses the same GTK tools): Document Scanner
      # (simple-scan) + Printers setup, like Mint Cinnamon.
      (lib.mkIf (isOcimum || isDwm) {
        environment.systemPackages = with pkgs; [
          simple-scan
          system-config-printer
        ];
      })

      # SonicDE (KDE): Skanlite + its print manager (print-manager is already
      # added in sonic-desktop.nix when printing is on; listed again harmlessly
      # if that changes). system-config-printer stays for driver setup.
      (lib.mkIf isSonic {
        environment.systemPackages = [
          pkgs.system-config-printer
          config.sonic.desktop.packages.skanlite
        ];
      })
    ]
  );
}
