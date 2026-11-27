# TulsiOS translations

TulsiOS' own strings are translated with gettext, in one catalogue for the whole
repo (ADR 0024). This directory holds it:

| File | What it is | Who edits it |
|---|---|---|
| `POTFILES` | The source files with translatable strings, one per line, relative to the repo root | Developers, when a file gains strings |
| `tulsios.pot` | The template: every English string, extracted from `POTFILES` | Regenerated (see below), never by hand |
| `languages.txt` | The languages to translate into (the installer's list, in gettext codes) | Developers |
| `<code>.po` | One language's translations, e.g. `sv.po`, `pt_BR.po`, `sr@latin.po` | Translators |

There is no `LINGUAS` file: the build makes one from the `.po` files that exist,
so a language appears as soon as its `.po` file is added.

Starah's window (Agent Privileges, Compare Levels, Agent Request) has its own
catalogue, in the Starah repository's `po/`, with the same 78 languages and a brief
of its own (`po/README.md` there). If you are translating both, do them in the
same session, with the same terms.

## Today: the AI Agents launcher

Only one file is translated so far:
`apps/ocimum-software-center/data/org.tulsi.AIAgents.desktop.in`, the launcher
on the desktops (Ocimum's desktop, SonicDE's panel, every app menu). The
Software Center's build (`nix/packages/ocimum-software-center.nix`) runs
`msgfmt --desktop`, which adds `Name[xx]=`, `GenericName[xx]=`, `Comment[xx]=`,
`Keywords[xx]=` and the action's `Name[xx]=` from each `po/xx.po`.

The strings (see `tulsios.pot`):

| msgid | Where it shows | Notes |
|---|---|---|
| `AI Agents` | The icon's label on the desktop, the menu entry | Short: about 20 characters at most, or the desktop label wraps. Keep "AI" if that is what people say in the language (many do); otherwise the usual abbreviation (KI, IA, ИИ…). |
| `AI Coding Agents` | The menu's generic name | |
| `Install AI coding agents and check which local models your computer can run` | Tooltip / menu comment | One sentence, no final period. |
| `AI;agent;LLM;model;assistant;Claude;Codex;OpenCode;Gemini;Ollama;llama;` | Menu search keywords | Translate the words, keep the product names, keep the `;` separators and the final `;`. Adding local synonyms is welcome. |
| `Check My Hardware` | Right-click action on the launcher | Title Case only where the language uses it. |

## For the translating agent: what to do

1. **Make sure the template is current.** From the repo root, in the dev shell
   (`nix develop`) or with `nix shell nixpkgs#gettext`:
   ```sh
   xgettext --language=Desktop --from-code=UTF-8 -k -kName -kGenericName -kComment -kKeywords \
     --package-name=TulsiOS --msgid-bugs-address=https://github.com/lukskrp/TulsiOS \
     -f po/POTFILES -o po/tulsios.pot
   ```
2. **Create one `.po` file per line of `languages.txt`** (skip lines starting with `#`):
   ```sh
   grep -v '^#' po/languages.txt | while read -r code; do
     [ -e "po/$code.po" ] || msginit --no-translator -l "$code" -i po/tulsios.pot -o "po/$code.po"
   done
   ```
   Then in each file set `"Content-Type: text/plain; charset=UTF-8\n"` and
   `"Language: <code>\n"`, and fill in every `msgstr`. Leave `msgid` untouched.
   Where you are unsure of a language, leave its `msgstr ""` empty rather than
   guess: empty strings fall back to English.
3. **Updating later** (the template changed): `msgmerge -U po/<code>.po po/tulsios.pot`
   for each file, then translate the new or `#, fuzzy` entries and remove the
   `fuzzy` marks.
4. **Check:**
   ```sh
   for f in po/*.po; do msgfmt -c -o /dev/null "$f" || echo "BROKEN: $f"; done
   git add po/*.po          # flakes only see files git knows about
   nix build .#ocimum-software-center
   grep -c '^Name\[' result/share/applications/org.tulsi.AIAgents.desktop   # 2 per language
   ```
5. **Don't edit** `org.tulsi.AIAgents.desktop.in` to add `Name[xx]=` lines by
   hand: the build generates them.

## Not translated yet

The Software Center's window (page titles such as "AI Agents", the hardware
check's output) and the other TulsiOS apps don't mark their strings for gettext
yet. That is a later step: mark strings with `_()`, list the Python files in
`POTFILES`, install `.mo` files from the same `.po` files. The catalogue and
the language list here are meant to grow into it.
