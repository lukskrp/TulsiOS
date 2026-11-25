# tulsi.drivers: hardware drivers in a few plain settings (ADR 0029).
#
# The Drivers app (and `tulsi-drivers set`) detects the machine's GPUs and Wi-Fi
# and writes these settings into configuration.nix, in a block marked
# "# Drivers (from the Drivers app)". This module turns them into NixOS's own
# options: hardware.nvidia.*, hardware.graphics.*, hardware.amdgpu.*, the
# Broadcom STA module. Evaluation can't see the hardware; the app does that.
#
# AMD and Intel GPUs work without any of this (amdgpu, modesetting); the settings
# here add video acceleration, compute and 32-bit games. NVIDIA's driver and
# Broadcom's are unfree: they need `nixpkgs.config.allowUnfree = true;`, which the
# app writes after the person accepts.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.tulsi.drivers;
  nv = cfg.nvidia;
  kp = config.boot.kernelPackages;
  nvPackage = kp.nvidiaPackages.${nv.branch};
  allowsUnfree = config.nixpkgs.config.allowUnfree or false;
  busId = lib.types.strMatching "(PCI:[0-9]{1,3}:[0-9]{1,2}:[0-9])?";
  branches = [
    "production"
    "new_feature"
    "beta"
    "legacy_580"
    "legacy_535"
    "legacy_470"
  ];
  # Why an NVIDIA series can't be used here, or null.
  unavailable =
    b:
    let
      broken = builtins.tryEval (kp.nvidiaPackages.${b}.meta.broken or false);
    in
    if cfg.unsupportedBranches ? ${b} then
      cfg.unsupportedBranches.${b}
    else if !broken.success || broken.value then
      "It doesn't build with Linux ${kp.kernel.version}."
    else
      null;
in
{
  options.tulsi.drivers = {
    app.enable = lib.mkOption {
      type = lib.types.bool;
      default =
        (config.ocimum.desktop.enable || config.sonic.desktop.enable || config.tulsi.dwm.enable)
        && !config.tulsi.installer.enable;
      defaultText = lib.literalMD "on with any TulsiOS desktop, except the live installer";
      description = "The Drivers app and the `tulsi-drivers` command.";
    };
    app.package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ../packages/tulsi-drivers.nix { };
      defaultText = lib.literalExpression "pkgs.callPackage ../packages/tulsi-drivers.nix { }";
      description = "The Drivers package.";
    };

    nvidia = {
      enable = lib.mkEnableOption "NVIDIA's own driver (unfree) instead of Nouveau";
      branch = lib.mkOption {
        type = lib.types.enum branches;
        default = "production";
        description = ''
          The driver series. `production` supports Turing (GeForce 16xx/RTX 20xx)
          and newer; `legacy_580` Maxwell to Volta (GTX 9xx/10xx); `legacy_470`
          Kepler (GTX 6xx/7xx). The Drivers app picks it from the card.
        '';
      };
      open = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = ''
          NVIDIA's open kernel modules, which NVIDIA recommends for Turing and
          newer. Older cards need the proprietary modules (false).
        '';
      };
      prime = {
        mode = lib.mkOption {
          type = lib.types.enum [
            "none"
            "offload"
            "sync"
          ];
          default = "none";
          description = ''
            For laptops with two GPUs. `offload`: the integrated GPU draws the
            desktop and the NVIDIA GPU runs what asks for it ("Run with dedicated
            GPU", `nvidia-offload`), saving battery. `sync`: the NVIDIA GPU draws
            everything.
          '';
        };
        nvidiaBusId = lib.mkOption {
          type = busId;
          default = "";
          example = "PCI:1:0:0";
          description = "The NVIDIA GPU's PCI address, in decimal.";
        };
        intelBusId = lib.mkOption {
          type = busId;
          default = "";
          example = "PCI:0:2:0";
          description = "The Intel integrated GPU's PCI address, in decimal.";
        };
        amdgpuBusId = lib.mkOption {
          type = busId;
          default = "";
          description = "The AMD integrated GPU's PCI address, in decimal.";
        };
      };
    };

    amd = {
      compute = lib.mkEnableOption "OpenCL compute (ROCm) on AMD GPUs";
      legacySupport = lib.mkEnableOption "the amdgpu driver for GCN 1 and 2 cards (Radeon HD 7000 to R9 290), instead of radeon";
    };

    intel = {
      videoAcceleration = lib.mkOption {
        type = lib.types.nullOr (
          lib.types.enum [
            "media"
            "i965"
          ]
        );
        default = null;
        description = ''
          Hardware video decoding and encoding (VA-API) on Intel GPUs: `media`
          (intel-media-driver) for Broadwell (2014) and newer, `i965`
          (intel-vaapi-driver) for older GPUs.
        '';
      };
      compute = lib.mkEnableOption "OpenCL and Level Zero compute on Intel GPUs (Gen12 and newer)";
    };

    unsupportedBranches = lib.mkOption {
      type = lib.types.attrsOf lib.types.str;
      default = {
        # XLibre's log (checks.drivers-nvidia): the legacy X drivers (470 and
        # older) crash on XLibre's ABI unless XLibre is built with
        # -Dlegacy_nvidia_padding=true. The 470 kernel modules do build.
        legacy_470 = "NVIDIA's 470 X driver crashes with XLibre, TulsiOS's display server.";
      };
      description = ''
        NVIDIA series that can't be used although nixpkgs builds them, with the
        reason the Drivers app shows. Series nixpkgs marks broken for the kernel
        are unavailable anyway.
      '';
    };

    games32Bit = lib.mkEnableOption "32-bit graphics libraries, for Steam and older games";

    broadcomWifi.enable = lib.mkEnableOption ''
      Broadcom's STA ("wl") Wi-Fi driver (unfree, unmaintained) for the Broadcom
      cards that need it'';
  };

  config = lib.mkMerge [
    (lib.mkIf cfg.app.enable {
      environment.systemPackages = [ cfg.app.package ];
      # What this system can build, for the app: the kernel, and each NVIDIA
      # series' version and whether it builds with that kernel.
      environment.etc."tulsi/drivers.json".text = builtins.toJSON {
        kernel = kp.kernel.version;
        nvidia = lib.genAttrs branches (
          b:
          let
            p = kp.nvidiaPackages.${b};
          in
          {
            version = p.version or "";
            available = unavailable b == null;
            reason = if unavailable b == null then "" else unavailable b;
          }
        );
        broadcom = {
          available = !(kp.broadcom_sta.meta.broken or false);
          reason = "It doesn't build with Linux ${kp.kernel.version}.";
        };
        microcode = config.hardware.cpu.intel.updateMicrocode || config.hardware.cpu.amd.updateMicrocode;
      };
    })

    (lib.mkIf nv.enable {
      assertions = [
        {
          assertion = allowsUnfree;
          message = ''
            NVIDIA's driver is unfree: add `nixpkgs.config.allowUnfree = true;` to
            configuration.nix (the Drivers app does this when you accept NVIDIA's licence).'';
        }
        {
          assertion = unavailable nv.branch == null;
          message = ''
            NVIDIA's ${nv.branch} driver (${nvPackage.version or "?"}) can't be used here:
            ${toString (unavailable nv.branch)} Use Nouveau (turn tulsi.drivers.nvidia.enable off).'';
        }
        {
          assertion = nv.open -> (nvPackage ? open);
          message = "NVIDIA's ${nv.branch} driver has no open kernel modules: set tulsi.drivers.nvidia.open = false;";
        }
        {
          assertion =
            nv.prime.mode != "none"
            -> nv.prime.nvidiaBusId != "" && (nv.prime.intelBusId != "" || nv.prime.amdgpuBusId != "");
          message = "tulsi.drivers.nvidia.prime needs nvidiaBusId and intelBusId or amdgpuBusId.";
        }
      ];

      # The 470 series also asks for NVIDIA's licence to be accepted by name;
      # choosing it in the app (with its licence shown) is that acceptance.
      # (nixpkgs.config is untyped below its top: the condition goes around it.)
      nixpkgs.config = lib.mkIf (nv.branch == "legacy_470") { nvidia.acceptLicense = true; };
      services.xserver.videoDrivers = [ "nvidia" ];
      hardware.graphics.enable = true;
      hardware.nvidia = {
        package = nvPackage;
        inherit (nv) open;
        modesetting.enable = true;
        # Suspend and resume keep the GPU's memory; on laptops in offload mode the
        # GPU also powers off when idle (Turing and newer).
        powerManagement.enable = true;
        powerManagement.finegrained = nv.prime.mode == "offload" && nv.open;
        prime = lib.mkIf (nv.prime.mode != "none") {
          inherit (nv.prime) nvidiaBusId intelBusId amdgpuBusId;
          offload.enable = nv.prime.mode == "offload";
          offload.enableOffloadCmd = nv.prime.mode == "offload";
          sync.enable = nv.prime.mode == "sync";
        };
      };
      # "Run with dedicated GPU" in Cinnamon's menu and Nemo.
      services.switcherooControl.enable = nv.prime.mode == "offload";
    })

    (lib.mkIf cfg.amd.compute { hardware.amdgpu.opencl.enable = true; })
    (lib.mkIf cfg.amd.legacySupport { hardware.amdgpu.legacySupport.enable = true; })

    (lib.mkIf (cfg.intel.videoAcceleration != null) {
      hardware.graphics.enable = true;
      hardware.graphics.extraPackages = [
        (if cfg.intel.videoAcceleration == "media" then pkgs.intel-media-driver else pkgs.intel-vaapi-driver)
      ];
      hardware.graphics.extraPackages32 = lib.mkIf cfg.games32Bit [
        (
          if cfg.intel.videoAcceleration == "media" then
            pkgs.driversi686Linux.intel-media-driver
          else
            pkgs.driversi686Linux.intel-vaapi-driver
        )
      ];
      environment.sessionVariables.LIBVA_DRIVER_NAME =
        if cfg.intel.videoAcceleration == "media" then "iHD" else "i965";
    })
    (lib.mkIf cfg.intel.compute {
      hardware.graphics.enable = true;
      hardware.graphics.extraPackages = [ pkgs.intel-compute-runtime ];
    })

    (lib.mkIf cfg.games32Bit {
      hardware.graphics.enable = true;
      hardware.graphics.enable32Bit = true;
    })

    (lib.mkIf cfg.broadcomWifi.enable {
      assertions = [
        {
          assertion = allowsUnfree;
          message = ''
            Broadcom's Wi-Fi driver is unfree: add `nixpkgs.config.allowUnfree = true;`
            to configuration.nix (the Drivers app does this when you accept).'';
        }
        {
          assertion = !(kp.broadcom_sta.meta.broken or false);
          message = "Broadcom's Wi-Fi driver doesn't build with Linux ${kp.kernel.version}.";
        }
      ];
      boot.extraModulePackages = [ kp.broadcom_sta ];
      boot.kernelModules = [ "wl" ];
      # The open drivers would claim the card first.
      boot.blacklistedKernelModules = [
        "b43"
        "bcma"
        "ssb"
        "brcmsmac"
      ];
      # Unmaintained, with known security problems; the app says so before turning it on.
      # (By name: naming the package itself here would make pkgs depend on itself.)
      nixpkgs.config.allowInsecurePredicate = pkg: lib.getName pkg == "broadcom-sta";
    })
  ];
}
