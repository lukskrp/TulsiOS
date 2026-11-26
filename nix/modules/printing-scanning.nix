# tulsi.printingScanning — printers and scanners that just work (Mint parity).
#
# Ocimum first, all desktops: CUPS with the common drivers, driverless
# discovery (Avahi/mDNS, cups-browsed, ipp-usb) and SANE with the AirScan
# backend, so USB and network printers/scanners mostly need no setup.
# The default drivers are all free software. Canon's, Samsung's and HP's own
# non-free drivers are opt-in (tulsi.printingScanning.unfreeDrivers, from the
# Drivers app), since they need unfree software turned on.
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
  # The unfree printer drivers Mint ships, opt-in here.
  unfreeDrivers = with pkgs; [
    cnijfilter2 # Canon PIXMA/MAXIFY
    samsung-unified-linux-driver
    hplipWithPlugin # HP's binary plugin (some LaserJets and scanners)
    foomatic-db-ppds-withNonfreeDb
  ];
in
{
  options.tulsi.printingScanning.enable = lib.mkOption {
    type = lib.types.bool;
    default = (isOcimum || isSonic || isDwm) && !config.tulsi.installer.enable;
    defaultText = lib.literalMD "on with any TulsiOS desktop, except the live installer";
    description = "Printers and scanners by default: CUPS drivers, Avahi discovery, SANE + AirScan, scanner app.";
  };

  options.tulsi.printingScanning.unfreeDrivers = lib.mkEnableOption ''
    the manufacturers' own non-free printer drivers (Canon PIXMA/MAXIFY, Samsung,
    HP's plugin, extra PPDs) for printers the free drivers don't run; they need
    `nixpkgs.config.allowUnfree = true;`'';

  config = lib.mkIf cfg.enable (
    lib.mkMerge [
      {
        services.printing = {
          enable = lib.mkDefault true;
          browsed.enable = lib.mkDefault true;
          drivers = with pkgs; [
            gutenprint
            gutenprintBin
            hplip
            splix
            brlaser
          ];
        };

        # Driverless USB (IPP-over-USB/AirPrint/WSD) and network discovery.
        services.ipp-usb.enable = lib.mkDefault true;
        # On PATH for debugging (the service itself runs from the store).
        environment.systemPackages = [ pkgs.ipp-usb ];
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

      (lib.mkIf cfg.unfreeDrivers {
        assertions = [
          {
            assertion = config.nixpkgs.config.allowUnfree or false;
            message = ''
              The manufacturers' printer drivers are unfree: add
              `nixpkgs.config.allowUnfree = true;` to configuration.nix (the Drivers
              app does this when you turn them on).'';
          }
        ];
        services.printing.drivers = unfreeDrivers;
      })

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
