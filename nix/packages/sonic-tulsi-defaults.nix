# TulsiOS defaults for SonicDE (ADR 0020), all of which users can change:
# - a look-and-feel, "TulsiOS (Silver)": Sonic's own default (Silver Light with
#   a bottom panel) plus the Tulsi Leaf wallpaper, the TulsiOS start button, and
#   the panel's pinned apps: files, browser, terminal, Software Center, Assistant;
# - chosen for new users through /etc/xdg/kdeglobals;
# Super+A for the Assistant is X-KDE-Shortcuts in the Assistant's own .desktop
# file, which kglobalacceld reads (its kglobalshortcutsrc has no /etc/xdg cascade).
{
  lib,
  runCommand,
  python3,
  silver,
  cinnamon,
}:

let
  base = "org.kde.silverlightbottompanel.desktop";
  id = "org.tulsios.sonic.desktop";
  ocimum = "${cinnamon.src}/files/usr/share";
  wallpaper = "${ocimum}/backgrounds/ocimum/tulsios-leaf.png";
  launchers = [
    "preferred://filemanager"
    "preferred://browser"
    "applications:org.kde.konsole.desktop"
    "applications:org.tulsi.SoftwareCenter.desktop"
    "applications:org.tulsi.Assistant.desktop"
  ];
  layout = ''
    // TulsiOS (Silver): Sonic's bottom panel, with TulsiOS's start button,
    // pinned apps and wallpaper. Runs once, for a new user's first session.
    loadTemplate("org.kde.silver.plasma.desktop.bottomPanel");

    const kwinConfig = ConfigFile('kwinrc');
    kwinConfig.group = 'Effect-overview';
    kwinConfig.writeEntry('BorderActivate', '9');
    kwinConfig.group = 'Effect-windowview';
    kwinConfig.writeEntry('BorderActivateAll', '3');

    panels().forEach(function (panel) {
      panel.widgets().forEach(function (widget) {
        if (widget.type === "org.kde.plasma.taskmanager" || widget.type === "org.kde.plasma.icontasks") {
          widget.currentConfigGroup = ["General"];
          widget.writeConfig("launchers", ${builtins.toJSON (lib.concatStringsSep "," launchers)});
          widget.reloadConfig();
        }
        if (widget.type === "org.kde.plasma.kickoff") {
          widget.currentConfigGroup = ["General"];
          widget.writeConfig("icon", "tulsi-start");
          widget.reloadConfig();
        }
      });
    });

    desktops().forEach(function (desktop) {
      desktop.wallpaperPlugin = "org.kde.image";
      desktop.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
      desktop.writeConfig("Image", "file://${wallpaper}");
    });
  '';
in
runCommand "sonic-tulsi-defaults"
  {
    nativeBuildInputs = [ python3 ];
    passthru = { inherit id launchers; };
    meta.description = "TulsiOS defaults for SonicDE: look-and-feel, panel and shortcuts";
  }
  ''
    lnf=$out/share/plasma/look-and-feel/${id}
    mkdir -p $out/share/plasma/look-and-feel
    cp -r ${silver}/share/plasma/look-and-feel/${base} $lnf
    chmod -R u+w $lnf

    # Its own id and name; the rest is Sonic's default.
    python3 - $lnf/metadata.json <<'EOF'
    import json, sys
    p = sys.argv[1]
    m = json.load(open(p))
    m["KPlugin"] = {k: v for k, v in m["KPlugin"].items() if not k.startswith(("Name[", "Description["))}
    m["KPlugin"].update(Id="${id}", Name="TulsiOS (Silver)",
                        Description="Silver Light with a bottom panel, TulsiOS's apps pinned and its wallpaper",
                        Website="https://github.com/lukskrp/TulsiOS")
    json.dump(m, open(p, "w"), indent=4)
    EOF
    rm -f $lnf/contents/layouts/*.js
    cat > $lnf/contents/layouts/org.sonicde.desktop-layout.js <<'EOF'
    ${layout}
    EOF

    # New users start with it.
    mkdir -p $out/etc/xdg
    cat > $out/etc/xdg/kdeglobals <<'EOF'
    [KDE]
    LookAndFeelPackage=${id}
    EOF

    # The TulsiOS start button's icon (from the Ocimum fork's sources).
    install -Dm644 ${ocimum}/icons/hicolor/scalable/apps/tulsi-start.svg \
      $out/share/icons/hicolor/scalable/apps/tulsi-start.svg

  ''
