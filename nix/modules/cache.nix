# tulsi.cache — download TulsiOS's own packages (Ocimum Desktop, GTK3-O, …)
# from the TulsiOS binary cache instead of building them. Everything that is
# identical to upstream keeps coming from cache.nixos.org.
{ config, lib, ... }:

let
  cfg = config.tulsi.cache;
in
{
  options.tulsi.cache = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Use the TulsiOS binary cache.";
    };

    url = lib.mkOption {
      type = lib.types.str;
      default = "https://cache.skarptech.org/tulsi";
      description = "Binary cache URL.";
    };

    publicKey = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      # Set once the cache server exists (deploy/attic/setup.sh prints it).
      default = null;
      example = "tulsi:AbCd…=";
      description = "Public signing key of the cache. Without it the cache is not used.";
    };
  };

  config = lib.mkIf cfg.enable (
    lib.mkMerge [
      (lib.mkIf (cfg.publicKey != null) {
        nix.settings = {
          substituters = [ cfg.url ];
          trusted-public-keys = [ cfg.publicKey ];
        };
      })
      (lib.mkIf (cfg.publicKey == null) {
        warnings = [
          "tulsi.cache.publicKey is not set, so TulsiOS packages are built locally instead of downloaded."
        ];
      })
    ]
  );
}
