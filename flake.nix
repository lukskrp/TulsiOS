{
  description = "TulsiOS — a NixOS-based distribution with the Ocimum Desktop";

  inputs = {
    # tulsipkgs: TulsiOS's fork of nixpkgs (Ocimum Desktop, GTK3-O, …).
    # Branch tulsi-unstable = upstream nixos-unstable + TulsiOS packages.
    nixpkgs.url = "github:lukskrp/tulsipkgs/tulsi-unstable";
    # Starah: levels of privilege for AI agents (ADR 0011).
    starah = {
      url = "github:lukskrp/starah";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      starah,
      ...
    }:
    let
      lib = nixpkgs.lib;
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems =
        f:
        lib.genAttrs systems (
          system:
          f (
            import nixpkgs {
              inherit system;
              overlays = [ self.overlays.default ];
            }
          )
        );
    in
    {
      # Adds TulsiOS packages to any nixpkgs.
      overlays.default = import ./nix/overlays { nixpkgs-src = nixpkgs.outPath; };

      # All TulsiOS NixOS modules (tulsi.state, tulsi.daemon, ocimum.*, ...),
      # plus defaults that need this flake's inputs.
      nixosModules.default =
        {
          config,
          lib,
          pkgs,
          ...
        }:
        {
          imports = [
            ./nix/modules
            starah.nixosModules.default
          ];
          # A bootstrapped system flake uses this source tree as its input…
          tulsi.daemon.bootstrap.source = lib.mkDefault self.outPath;
          # …and needs the pinned inputs' sources to evaluate offline (as does the
          # installer, which builds the new system from the same flake).
          system.extraDependencies =
            lib.mkIf (config.tulsi.daemon.bootstrap.enable || config.tulsi.installer.enable)
              [
                nixpkgs.outPath
                starah.outPath
              ];
          # The pinned nixpkgs, for tulsi-mcp's packaging tools (agent-built local packages).
          environment.etc."tulsi/nixpkgs".source = nixpkgs.outPath;
          tulsi.daemon.packageIndex = lib.mkDefault (
            pkgs.callPackage ./nix/packages/package-index.nix { nixpkgsSrc = nixpkgs.outPath; }
          );
          # GTK3-O comes from tulsipkgs.
          ocimum.gtk3o.package = lib.mkDefault pkgs.gtk3-o;
        };

      packages = forAllSystems (pkgs: {
        inherit (pkgs)
          tulsi-tools
          gtk3-o
          tulsi-package-index
          ocimum-software-center
          ocimum-assistant
          ocimum-greeter
          tulsi-installer
          calamares-tulsios-extensions
          ;
        default = pkgs.tulsi-tools;
      }
      # The live ISO (hybrid: also the dd image for USB sticks), ADR 0016.
      // lib.optionalAttrs (pkgs.stdenv.hostPlatform.system == "x86_64-linux") {
        iso = self.nixosConfigurations.tulsi-iso.config.system.build.isoImage;
      });

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = with pkgs; [
            cargo
            rustc
            rustfmt
            clippy
            rust-analyzer
            nixfmt
            nil
            jq
            git
            (python3.withPackages (ps: [
              ps.pygobject3
              ps.pytest
              ps.anthropic
            ]))
            gtk3
            libsecret
            xapp
            gobject-introspection
          ];
          # Cargo looks up subcommands (fmt, clippy) in $CARGO_HOME/bin before
          # PATH; keep a user-wide rustup install from shadowing the pinned tools.
          shellHook = ''
            export CARGO_HOME="$PWD/.cargo-home"
          '';
        };
      });

      formatter = forAllSystems (pkgs: pkgs.nixfmt-tree);

      nixosConfigurations.tulsi-vm = lib.nixosSystem {
        modules = [
          self.nixosModules.default
          ./nix/hosts/vm
        ];
      };

      nixosConfigurations.tulsi-iso = lib.nixosSystem {
        modules = [
          self.nixosModules.default
          (import ./nix/hosts/iso { inherit self; })
        ];
      };

      checks.x86_64-linux =
        let
          pkgs = import nixpkgs {
            system = "x86_64-linux";
            overlays = [ self.overlays.default ];
          };
          test = file: pkgs.testers.runNixOSTest (import file { inherit self; });
        in
        {
          inherit (pkgs)
            tulsi-tools
            ocimum-software-center
            ocimum-assistant
            ocimum-greeter
            tulsi-installer
            calamares-tulsios-extensions
            ;
          gtk3-o-abi = pkgs.gtk3-o.abiCheck;
          vm-toplevel = self.nixosConfigurations.tulsi-vm.config.system.build.toplevel;
          state-packages = test ./nix/tests/state-packages.nix;
          tulsid = test ./nix/tests/tulsid.nix;
          software-center = test ./nix/tests/software-center.nix;
          browser-extensions = test ./nix/tests/browser-extensions.nix;
          mcp = test ./nix/tests/mcp.nix;
          assistant = test ./nix/tests/assistant.nix;
          ocimum-desktop = test ./nix/tests/ocimum-desktop.nix;
          greeter-login = test ./nix/tests/ocimum-greeter.nix;
          starah-setup = test ./nix/tests/starah-setup.nix;
          adopt = test ./nix/tests/adopt.nix;
          # ADR 0016: the dwm session, and installing each desktop onto an empty disk.
          dwm-session = test ./nix/tests/dwm-session.nix;
          install-dwm = pkgs.testers.runNixOSTest (
            import ./nix/tests/install.nix {
              inherit self;
              desktop = "dwm";
            }
          );
          install-ocimum = pkgs.testers.runNixOSTest (
            import ./nix/tests/install.nix {
              inherit self;
              desktop = "ocimum";
            }
          );
          # Installing with the ISO's own reference installs, onto QEMU hardware they
          # weren't made for, in a combination neither has (dwm with UEFI).
          install-iso-references = pkgs.testers.runNixOSTest (
            import ./nix/tests/install.nix {
              inherit self;
              desktop = "dwm";
              references = import ./nix/hosts/iso/references.nix {
                inherit self;
                testing = true;
              };
            }
          );
          # The ISO's live session (Ocimum + Calamares), without building an ISO.
          live-session = test ./nix/tests/live-session.nix;
          # The live ISO boots (UEFI and BIOS) into the live session with Calamares.
          iso-boot = pkgs.testers.runNixOSTest (import ./nix/tests/iso-boot.nix { inherit self pkgs; });
          # A state with a local package (tulsi/pkgs/<name>/package.nix) installs it.
          local-package-eval =
            let
              system = lib.nixosSystem {
                modules = [
                  self.nixosModules.default
                  ./nix/hosts/vm
                  { tulsi.state.file = lib.mkForce ./nix/tests/local/state.json; }
                ];
              };
              names = map (p: p.pname or "") system.config.environment.systemPackages;
            in
            assert builtins.elem "frob" names;
            pkgs.writeText "local-package-eval" "frob is installed from tulsi/pkgs/frob";
        };
    };
}
