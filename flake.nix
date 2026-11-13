{
  description = "TulsiOS — a NixOS-based distribution with the Ocimum Desktop";

  inputs = {
    # tulsipkgs: TulsiOS's fork of nixpkgs (Ocimum Desktop, GTK3-O, …).
    # Branch tulsi-unstable = upstream nixos-unstable + TulsiOS packages.
    nixpkgs.url = "github:lukskrp/tulsipkgs/tulsi-unstable";
  };

  outputs =
    {
      self,
      nixpkgs,
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
          imports = [ ./nix/modules ];
          # A bootstrapped system flake uses this source tree as its input…
          tulsi.daemon.bootstrap.source = lib.mkDefault self.outPath;
          # …and needs the pinned nixpkgs source to evaluate offline.
          system.extraDependencies = lib.mkIf config.tulsi.daemon.bootstrap.enable [ nixpkgs.outPath ];
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

      checks.x86_64-linux =
        let
          pkgs = import nixpkgs {
            system = "x86_64-linux";
            overlays = [ self.overlays.default ];
          };
          test = file: pkgs.testers.runNixOSTest (import file { inherit self; });
        in
        {
          inherit (pkgs) tulsi-tools ocimum-software-center ocimum-assistant ocimum-greeter;
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
        };
    };
}
