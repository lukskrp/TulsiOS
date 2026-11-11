{
  description = "TulsiOS — a NixOS-based distribution with the Ocimum Desktop";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs =
    { self, nixpkgs, ... }:
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
      # Adds TulsiOS packages (tulsi-tools, later ocimum-*) to any nixpkgs.
      overlays.default = import ./nix/overlays;

      # All TulsiOS NixOS modules (tulsi.state, tulsi.daemon, ocimum.*, ...).
      nixosModules.default = import ./nix/modules;

      packages = forAllSystems (pkgs: {
        inherit (pkgs) tulsi-tools;
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
          ];
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
        in
        {
          tulsi-tools = pkgs.tulsi-tools;
          vm-toplevel = self.nixosConfigurations.tulsi-vm.config.system.build.toplevel;
          state-packages = pkgs.testers.runNixOSTest (
            import ./nix/tests/state-packages.nix { inherit self; }
          );
        };
    };
}
