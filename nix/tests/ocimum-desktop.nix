# Ocimum Desktop: the tulsipkgs Cinnamon fork is what gets installed, and the
# TulsiOS defaults (theme, wallpaper, menu icon, Assistant shortcut) apply.
{ self }:
{
  name = "ocimum-desktop";

  nodes.machine =
    { modulesPath, ... }:
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      ocimum.desktop.enable = true;
      virtualisation.memorySize = 2048;
    };

  testScript = ''
      machine.wait_for_unit("multi-user.target")

      with subtest("the installed desktop is the Ocimum fork"):
          names = machine.succeed("grep -h '^Name=' /run/current-system/sw/share/xsessions/*.desktop || "
                                  "grep -rh '^Name=' /nix/store/*-cinnamon-*-ocimum*/share/xsessions/")
          assert "Ocimum Desktop" in names, names
          machine.succeed("ls /run/current-system/sw/share/icons/hicolor/scalable/apps/ocimum-symbolic.svg")

      with subtest("TulsiOS defaults are the compiled gsettings defaults"):
          # The Cinnamon module exports the compiled overrides for the session.
          schemas = machine.succeed("bash -lc 'echo $NIX_GSETTINGS_OVERRIDES_DIR'").strip()
          machine.succeed(f"test -f {schemas}/gschemas.compiled")
          def default(schema, key):
              return machine.succeed(
                  f"GSETTINGS_SCHEMA_DIR={schemas} GSETTINGS_BACKEND=memory gsettings get {schema} {key}"
              ).strip()
          icon = default("org.cinnamon", "app-menu-icon-name")
          assert icon == "'ocimum-symbolic'", icon
          theme = default("org.cinnamon.desktop.interface", "gtk-theme")
          assert theme == "'Mint-Y-Dark'", theme
          uri = default("org.cinnamon.desktop.background", "picture-uri")
          assert "ocimum-wallpaper.svg" in uri, uri

      with subtest("Super+A opens the Assistant"):
          read = lambda key: machine.succeed(f"su - alice -c 'dconf read {key}'").strip()
          base = "/org/cinnamon/desktop/keybindings/custom-keybindings/custom0/"
          assert read("/org/cinnamon/desktop/keybindings/custom-list") == "['custom0']"
          assert read(base + "command") == "'ocimum-assistant'"
          assert read(base + "binding") == "['<Super>a']"
    '';
}
