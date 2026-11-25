---
name: tulsios-make-theme
description: >
  Make a new TulsiOS desktop theme from a look, mood or inspiration: a colors.toml
  palette (Omarchy's format) that tulsi-theme turns into the GTK, Cinnamon, KDE,
  terminal and dwm colours, plus optional backgrounds with their licences, in
  ~/.config/tulsi/themes/<slug>/, checked with `tulsi-theme look`, then applied.
  Triggers: make a theme, new theme, colour scheme, palette, theme inspired by.
  Switching to an existing theme is just `tulsi-theme set` (the tulsios skill).
---

# Making a TulsiOS theme

A theme is a directory `~/.config/tulsi/themes/<slug>/` (the slug becomes the
name: `tea-house` shows as "Tea House") holding:

- `colors.toml`: the palette. TulsiOS generates each desktop's theme from it when
  it is applied. The format is Omarchy's (github.com/omacom/omarchy, MIT), so
  Omarchy themes work too.
- `backgrounds/` (optional): `1-<name>.jpg`, `2-<name>.jpg`, … at least 1920x1080.
- `CREDITS.md`: where the colours and every background come from, and their
  licences. Without backgrounds the theme uses TulsiOS' Tulsi Leaf.

## Steps

1. Copy the `colors.toml` of a stock theme with the same `mode` (dark or light)
   from `/run/current-system/sw/share/tulsi/themes/` and change its values. Keep
   every key: `mode`, `accent`, `selection`, `muted`, `background`,
   `dark_background`, `darker_background`, `lighter_background`, `foreground`,
   `dark_foreground`, `light_foreground`, `bright_foreground`, `red`, `yellow`,
   `orange`, `green`, `cyan`, `blue`, `magenta`, `brown`, and `bright_` versions
   of red, yellow, green, cyan, blue and magenta.
   - Dark themes: the backgrounds get darker from `lighter_background` to
     `darker_background`. Light themes: `background` is the lightest, and the
     others step darker.
   - Keep `foreground` on `background` at 7:1 contrast or more, `accent` at 3:1.
2. **Backgrounds only with a licence that allows sharing them**: your own work,
   CC0, or a licence that permits redistribution, credited in `CREDITS.md`
   (title, author, licence, link). Never take wallpapers from another theme or
   distribution without that: Omarchy's, for instance, carry no licence.
3. `tulsi-theme look ~/.config/tulsi/themes/<slug>` draws the theme as a small
   desktop without applying it and lists problems. Open the PNG it prints, fix
   every problem, and look again until it is clean.
4. `tulsi-theme set <slug>` applies it; `tulsi-theme undo` goes back.

## Sharing a theme

A theme repository holds `colors.toml`, `backgrounds/`, `CREDITS.md` and a
`LICENSE`. `tulsi-theme install <git-url>` keeps only those (colours, images,
text); nothing in a theme can run code.
