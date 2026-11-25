# ADR 0021: Themes from palettes

Status: accepted (2026-11-25). Ocimum and dwm done; SonicDE's colour scheme
is written but not yet switched in its VM check.

## Context

Changing the look of a TulsiOS desktop meant picking a GTK theme, a Cinnamon
theme, icons, a terminal profile and a wallpaper separately, each from
whatever someone had packaged. Omarchy (github.com/omacom/omarchy, MIT,
© David Heinemeier Hansson) shows a simpler model: a theme is one
`colors.toml` with about 28 named colours and a folder of backgrounds, and
every program's colours are generated from it. Its keyboard-first Hyprland
desktop doesn't suit TulsiOS, but the palette format does, and Omarchy themes
are already plentiful.

## Decision

- **Format:** Omarchy's `colors.toml`, unchanged (keys, meaning, `mode = dark |
  light`), so Omarchy themes and theme repositories work as they are. A theme
  is a directory: `colors.toml`, optional `backgrounds/`, and `CREDITS.md` for
  stock themes. Stock themes are in `share/tulsi/themes`, a person's own and
  installed ones in `~/.config/tulsi/themes` (a user theme of the same name wins).
- **Translation, per desktop, at switch time** (`tulsi-theme`,
  `apps/ocimum-themes/tulsi_theme`):
  - **Ocimum:** Mint-Y recoloured the way Linux Mint builds its own colour
    variants (mint-themes' `generate-themes.py`): its SASS sources are copied,
    the light/dark block of each `_colors.scss` becomes the palette's values for
    its mode, and libsass compiles GTK 3 and Cinnamon CSS. The accent-coloured
    checkbox/radio/switch images are rendered again from `assets.svg` with the
    palette's accent, at Mint's own sizes. Icons: the Mint-Y icon colour nearest
    the accent's hue. GNOME Terminal gets a profile of its own (the user's are
    never touched). Generated themes are cached by palette and accent.
  - **SonicDE:** a KDE colour scheme (layout adapted from Omarchy's
    `qtengine.colors.tpl`), applied with Sonic's `plasma-apply-colorscheme` and
    `plasma-apply-wallpaperimage`; GTK apps there take the generated GTK theme.
  - **dwm:** X resources merged with xrdb. TulsiOS' dwm patch
    (`data/dwm/dwm-colours-xrdb-6.8.diff`) reads `dwm.normbgcolor` and the
    other five colours at start and again whenever the root window's
    `RESOURCE_MANAGER` changes, which `xrdb -merge` does, so the bars, borders
    and tray recolour at once with no signal or restart; dmenu takes dwm's
    colours. st's patch (`st-colours-xrdb-0.9.3.diff`) reads `*.color0-15`,
    foreground, background and cursor colour when a terminal opens. GTK apps
    get the generated theme in `~/.config/gtk-3.0/settings.ini` (dwm runs no
    settings daemon); the wallpaper is set with `xwallpaper` and recorded, and
    the session merges the resources and sets the wallpaper again at login.
    Only `#rrggbb` values are taken, since dwm and st exit on a colour they
    cannot allocate.
- **Per person, at once, no rebuild.** Everything is written under the
  person's home (`~/.local/share/themes/Tulsi-<slug>`) and switched with their
  own settings; the theme name changes with each switch so running GTK
  programs and Cinnamon reload it. A history makes `tulsi-theme undo` go back
  one switch at a time, down to the desktop's own look (its settings reset).
- **The Themes app** (`ocimum-themes`, GTK 3): theme cards drawn from each
  palette over its first background, a Dark/Light filter, a detail pane with
  the backgrounds and the credits, Use This Theme with an Undo bar, and
  Install from Git.
- **Installing from git** keeps only data: `colors.toml`, images, and licence /
  README / credits text. Scripts, `*.lua` and per-app configs are dropped, files
  are copied without their modes, and the licence is shown before the theme is
  used. Only `https://` and `git@host:` URLs are cloned.
- **Agents:** tulsi-mcp gains `list_themes`, `set_theme` and `undo_theme`. A
  theme is the person's own, undoable setting, so they need no approval; they
  work when tulsi-mcp runs in the person's session (a coding agent they
  started). An agent with its own identity under Starah has no session of the
  person's to change and is told to suggest the Themes app.

## Attribution

- Omarchy's MIT notice is kept in `apps/ocimum-themes/THIRD_PARTY.md`, for the
  format, the stock palettes' extra tones, the terminal colour order and the
  KDE scheme layout.
- Each stock palette credits its scheme's authors (Catppuccin, Tokyo Night,
  Nord, Gruvbox / Gruvbox Material, Rosé Pine, Kanagawa, Everforest, Flexoki;
  all MIT) and Omarchy, in its `colors.toml` header and `CREDITS.md`.
- **No Omarchy wallpapers are shipped.** The repository gives them no licence
  or credit, some are other people's artwork, and Omarchy's MIT notice can't
  license images it didn't make. Stock themes use TulsiOS' Tulsi Leaf until
  licensed, credited backgrounds are chosen for them.
- The dwm and st patches are TulsiOS' own (MIT, as dwm and st), written for
  dwm 6.8 with the systray patch and st 0.9.3.
- Mint-Y is Linux Mint's (GPL-3.0); it is recoloured at switch time, not forked.

## Consequences

- One palette themes every TulsiOS desktop, and the whole Omarchy theme
  ecosystem is installable (colours and images only).
- A first switch to a palette compiles Mint-Y (a few seconds); switching back
  is instant (cached).
- Mint-Y's GTK 4 / libadwaita styles are not recoloured (Ocimum has no GTK 4
  apps); GTK 2 apps keep Mint-Y-Dark.
- Follow-ups: backgrounds for the stock themes (licensed, credited, chosen by
  the maintainer); `checks.sonic-desktop` switching a
  palette; the Assistant switching themes for the person it serves.
