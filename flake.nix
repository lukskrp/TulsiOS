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
      nixosModules.default =
        { config, lib, ... }:
        {
          imports = [ ./nix/modules ];
          # A bootstrapped system flake uses this source tree as its input…
          tulsi.daemon.bootstrap.source = lib.mkDefault self.outPath;
          # …and needs the pinned nixpkgs source to evaluate offline.
          system.extraDependencies = lib.mkIf config.tulsi.daemon.bootstrap.enable [ nixpkgs.outPath ];
        };

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
        in
        {
          tulsi-tools = pkgs.tulsi-tools;
          vm-toplevel = self.nixosConfigurations.tulsi-vm.config.system.build.toplevel;
          state-packages = pkgs.testers.runNixOSTest (
            import ./nix/tests/state-packages.nix { inherit self; }
          );
          tulsid = pkgs.testers.runNixOSTest (import ./nix/tests/tulsid.nix { inherit self; });
        };
    };
}
