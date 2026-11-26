# ADR 0036: Web apps

Status: accepted (2026-11-26).

## Context

Much everyday software is a website: AI assistants (Claude, ChatGPT, Gemini),
mail, banking, music, documents. People want them in the menu and the task bar
like apps, in their own window, not lost among browser tabs. Mint does this with
its Web App Manager.

## Decision

- **Mint's Web App Manager** (1.4.9, Python and GTK3) is packaged in tulsipkgs
  (`pkgs/by-name/we/webapp-manager`) and installed on every desktop by
  `tulsi.utilities`. The package:
  - looks for browsers in `/run/current-system/sw/bin` instead of `/usr/bin`;
  - lists **Brave Origin first**, so new web apps use the TulsiOS browser;
  - shows its menu entry on KDE desktops too (SonicDE).
- **Each web app has its own browser profile** (Web App Manager's "isolated
  profile"): its own cookies and logins, separate from the person's main browser.
  Removing the app removes them.
- **Suggested web apps** on the Software Center's Featured page (`webapps.json`):
  Claude, ChatGPT, Gemini, Proton Mail, YouTube Music, Google Docs. Each is added to
  the menu only when the person clicks **Add to Menu**, and **Remove** takes it away
  again.
- **`tulsi-webapp add|list|remove`** (in the Software Center package) writes the
  same launchers as Web App Manager (`~/.local/share/applications/WebApp-*.desktop`),
  so Web App Manager lists and edits the suggested ones too. It fetches the site's
  own icon from the site itself; Web App Manager's icon search can also ask
  Google's favicon service, `tulsi-webapp` doesn't.
- Agents can add web apps with `tulsi-webapp`: it only writes in the person's own
  menu folder.

## Consequences

- A website becomes a menu app in one click, isolated from the main browser.
- Web App Manager also supports Firefox and other browsers, if the person picks
  them in its window.
- The package comes from Mint's `master.mint27` tag; updates follow Mint's tags.
- `checks.webapps` adds an app with `tulsi-webapp`, checks the launcher, starts Web
  App Manager (with a screenshot) and removes the app.
