{
  description = "TulsiOS — a NixOS-based distribution with the Ocimum Desktop";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    # GTK3-O, the Ocimum fork of GTK 3.24 (ABI-compatible). Update with
    # `nix flake update gtk3-o`.
    gtk3-o = {
      url = "github:lukskrp/GTK3-24-Fork-Imprv/gtk-3-24";
      flake = false;
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      gtk3-o,
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
      overlays.default = import ./nix/overlays {
        gtk3-o-src = gtk3-o;
        nixpkgs-src = nixpkgs.outPath;
      };

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
          imports = [ ./nix/modules ];
          # A bootstrapped system flake uses this source tree as its input…
          tulsi.daemon.bootstrap.source = lib.mkDefault self.outPath;
          # …and needs the pinned nixpkgs source to evaluate offline.
          system.extraDependencies = lib.mkIf config.tulsi.daemon.bootstrap.enable [ nixpkgs.outPath ];
          tulsi.daemon.packageIndex = lib.mkDefault (
            pkgs.callPackage ./nix/packages/package-index.nix { nixpkgsSrc = nixpkgs.outPath; }
          );
          ocimum.gtk3o.package = lib.mkDefault (pkgs.callPackage ./nix/packages/gtk3-o.nix { src = gtk3-o; });
        };

      packages = forAllSystems (pkgs: {
        inherit (pkgs)
          tulsi-tools
          gtk3-o
          tulsi-package-index
          ocimum-software-center
          ;
        default = pkgs.tulsi-tools;
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
            ]))
            gtk3
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

      checks.x86_64-linux =
        let
          pkgs = import nixpkgs {
            system = "x86_64-linux";
            overlays = [ self.overlays.default ];
          };
          test = file: pkgs.testers.runNixOSTest (import file { inherit self; });
        in
        {
          inherit (pkgs) tulsi-tools ocimum-software-center;
          gtk3-o-abi = pkgs.gtk3-o.abiCheck;
          vm-toplevel = self.nixosConfigurations.tulsi-vm.config.system.build.toplevel;
          state-packages = test ./nix/tests/state-packages.nix;
          tulsid = test ./nix/tests/tulsid.nix;
          software-center = test ./nix/tests/software-center.nix;
          browser-extensions = test ./nix/tests/browser-extensions.nix;
        };
    };
}
