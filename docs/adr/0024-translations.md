# ADR 0024: Translations

Status: accepted (2026-11-25); first catalogue drafted, translations pending.

## Context

TulsiOS' own apps and launchers were English only: no gettext, no `po/`, no
`Name[xx]=` lines. The installer offers about 80 languages, through Calamares'
own catalogues, and every glibc locale is built in (`i18n.supportedLocales =
[ "all" ]`). The first string that has to follow the person's language is the
AI Agents launcher's name on their desktop (ADR 0023).

## Decision

- **One gettext catalogue for the repo:** domain `tulsios`, in `po/` at the
  root. `po/POTFILES` lists the source files and `po/tulsios.pot` is generated
  from them with `xgettext`. There is one `po/<code>.po` per language.
- **The languages are the installer's:** Calamares 3.4.2's list, all tiers, in
  gettext codes, in `po/languages.txt` (78 languages; how the codes were mapped
  is noted there). The build takes its `LINGUAS` from the `.po` files present,
  so a missing translation never breaks it.
- **Launchers are translated at build time:** each `.desktop.in` goes through
  `msgfmt --desktop`, which writes `Name[xx]=`, `Comment[xx]=`,
  `Keywords[xx]=` and the actions' names. Nobody adds them by hand.
- **Translations can be made by an agent and reviewed like code.**
  `po/README.md` is the brief: which files, which strings, length limits, and
  how to check them (`msgfmt -c`, a build, `grep Name[`). Empty `msgstr` falls
  back to English, so a partial translation is safe.

## Consequences

- The Python apps' own strings are not marked yet. Doing it is mechanical:
  `_()` around strings, the files listed in `POTFILES`, `.mo` files installed
  from the same `.po` files. It stays out of this change.
- Calamares keeps its own translations; TulsiOS' Calamares modules use them.

## Verification

With a throwaway `po/sv.po`, the built launcher contains `Name[sv]=AI-agenter`
and the action's `Name[sv]=`. The file was not committed.
