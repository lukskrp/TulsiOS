# The TulsiOS Wiki: docs/wiki/*.md as HTML pages on the computer, opened in the
# browser from the app menu (TulsiOS Wiki), the Welcome window, Starah's Agent
# Privileges, or `tulsi-wiki [PAGE]`.
{
  lib,
  runCommand,
  cmark-gfm,
  writeShellScriptBin,
  makeDesktopItem,
  symlinkJoin,
  xdg-utils,
}:

let
  pages = runCommand "tulsi-wiki-pages" { nativeBuildInputs = [ cmark-gfm ]; } ''
    out=$out/share/tulsios/wiki
    mkdir -p $out
    for md in ${../../docs/wiki}/*.md; do
      name=$(basename "$md" .md)
      title=$(sed -n '1s/^# //p' "$md")
      {
        cat <<EOF
    <!doctype html>
    <html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>$title · TulsiOS Wiki</title>
    <style>
      :root { --bg: #fbfcfb; --fg: #1d221e; --dim: #5a655c; --accent: #3f8a4f; --line: #d9e0da; --code: #eef2ef; }
      @media (prefers-color-scheme: dark) {
        :root { --bg: #1b1f1c; --fg: #e3e8e4; --dim: #a3ada5; --accent: #7cc48b; --line: #3a423c; --code: #262b27; }
      }
      body { background: var(--bg); color: var(--fg); font: 16px/1.6 system-ui, sans-serif;
             max-width: 46rem; margin: 0 auto; padding: 1.5rem 1rem 4rem; }
      a { color: var(--accent); }
      nav { font-size: .9rem; color: var(--dim); margin-bottom: 1rem; }
      h1 { margin-top: .5rem; } h2 { margin-top: 2rem; border-bottom: 1px solid var(--line); }
      code { background: var(--code); padding: .1em .3em; border-radius: 4px; }
      table { border-collapse: collapse; width: 100%; }
      th, td { border: 1px solid var(--line); padding: .4rem .6rem; text-align: left; vertical-align: top; }
    </style></head><body>
    <nav><a href="index.html">TulsiOS Wiki</a></nav>
    EOF
        cmark-gfm --extension table --extension autolink "$md"
        echo '</body></html>'
      } > "$out/$name.html"
    done
  '';

  command = writeShellScriptBin "tulsi-wiki" ''
    # tulsi-wiki [PAGE]: a page of the TulsiOS Wiki in the browser (index by default).
    page=''${1:-index}
    file=${pages}/share/tulsios/wiki/''${page%.html}.html
    if [ ! -e "$file" ]; then
      echo "tulsi-wiki: no page \"$page\"; the pages are:" >&2
      ls ${pages}/share/tulsios/wiki | sed 's/\.html$//' >&2
      exit 1
    fi
    exec ${xdg-utils}/bin/xdg-open "$file"
  '';

  desktop = makeDesktopItem {
    name = "org.tulsi.Wiki";
    desktopName = "TulsiOS Wiki";
    comment = "Help for TulsiOS: AI agents and Starah, your files' history, disk space";
    exec = "tulsi-wiki";
    icon = "help-browser";
    categories = [
      "System"
      "Documentation"
    ];
    keywords = [
      "help"
      "manual"
      "wiki"
      "agents"
      "starah"
    ];
  };
in
symlinkJoin {
  name = "tulsi-wiki";
  paths = [
    pages
    command
    desktop
  ];
  meta = {
    description = "The TulsiOS Wiki, offline";
    license = lib.licenses.mit;
    mainProgram = "tulsi-wiki";
  };
}
