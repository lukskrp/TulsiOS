# ADR 0019: Write it yourself, with help: the Nix Editor

Status: accepted (2026-11-24).

## Context

ADR 0018 gives TulsiOS two ways to package a download that has no TulsiOS package:
- **Recipes,** which need no model;
- **the Assistant,** which needs an AI model, from a provider or run locally.

A Recipe can fail. Its templates may not fit the software, or a library may be missing that the tables don't know. When it fails on a computer with no model, the person is stuck.

The Recipe's draft `package.nix` and its build log are on disk (`~/.local/share/tulsi/recipes/NAME/`). But TulsiOS has no editor that helps with Nix:
- the desktop's text editor (xed) has no language-server support;
- no editor we know of puts a Nix guide beside the file.

## Decision

**TulsiOS has its own Nix Editor** (`apps/ocimum-nix-editor`, `ocimum-nix-editor`). It is Python, GTK 3 and GtkSourceView 4, like the Software Center, so the system-wide graft gives it GTK3-O.

**Files open in tabs, with problems and the build log below them.**
- GtkSourceView's own `nix` highlighting, with line numbers, bracket matching, and two-space indentation.
- **[nixd](https://github.com/nix-community/nixd)** is wrapped into the package and spoken to over the Language Server Protocol (`lsp.py`, a small client driven by the GLib main loop). It provides:
  - **completion:** Ctrl+Space, or as you type;
  - **hover text:** for example a package's description;
  - **problems:** marked as you type.
- **nixd evaluates the system's pinned nixpkgs** (`/etc/tulsi/nixpkgs`), the same one Recipes build against. Completion therefore offers what will build, and works offline.
- **NixOS options are not completed.** People on TulsiOS write packages, not `configuration.nix` (state.json holds the system's choices).
- **TulsiOS's own rules** for local packages (`tulsi_state::check_expression`) are checked when a `package.nix` is opened or saved (`tulsi recipe check FILE`). They are listed with nixd's problems and placed on the code they quote.
- **A file that another program changes is reloaded,** unless it has unsaved edits.
- **Dark and light follow the desktop theme, live.** Cinnamon's Themes, or any XSETTINGS change, switches the window with GTK. The code's colours (GtkSourceView's `oblivion` or `classic`) follow the theme's own background colour, so any dark theme counts, not only ones named "Dark".
- **If nixd is missing or stops,** the editor keeps working without it and says so.

**A Nix guide on the right, written for TulsiOS** (`ocimum_nix_editor/guide/*.md`).
- **Short entries,** each with an example:
  - the language;
  - the builtins people meet;
  - `lib`;
  - packaging: `mkDerivation`, phases, inputs, fetchers and hashes, `autoPatchelfHook`, wrappers, Rust, Go, AppImages, menu entries;
  - TulsiOS: what a local package must look like, `requireFile`, what is refused, reading a build log, kept downloads, proprietary software.
- **The guide follows the cursor.** The word under it shows its entry. A name the guide doesn't know shows nixd's hover text instead, so a package shows its description.
- **Search, contents, links, Insert Example.**
- **Completion offers the guide's snippets,** for example a `stdenv.mkDerivation { … }` skeleton.
- **Why our own text:**
  - it is written for the person who meets Nix through a failed Recipe;
  - it works offline;
  - its licence is ours.
- **The checks** (`checks.nix-guide`): every example parses, the packaging and TulsiOS examples pass TulsiOS's rules, and every link leads somewhere.

**Edit It Yourself.**
- When a Recipe fails, the install window offers **Edit It Yourself** beside Ask the Assistant, whether or not a model is set up.
- It opens the draft in the editor (`ocimum-nix-editor --draft DIR`), with the Recipe's last build log (`build.log`) below.
- In a draft, the editor has **Build and Try** and **Install**.
- **Build and Try** saves the file and runs `tulsi recipe build-draft DIR`:
  - the same safety check, Nix sandbox and bubblewrap try as a Recipe;
  - no automatic fixes: the person's text is built as written;
  - the answers come from `recipe.json`, which every Recipe now writes beside its draft;
  - a draft edited to `lib.licenses.unfree` is installed with its licence accepted.
- **Install** turns the result into ops (`tulsi recipe ops RESULT.json`) and hands them to the Software Center's `apply-ops`. It gets the usual confirmation, history, kept download and Undo, and the origin `edited:…` in `meta.json`.

**The editor is on by default on the Ocimum desktop** (`ocimum.nixEditor.enable`). It is also the default application for `.nix` files (`text/x-nix`).

## Consequences

- **Without a model, a failed Recipe is no longer a dead end.** The person sees the log, the guide explains the words in front of them, and nixd finds package names.
- **nixd adds to the system's size.** It brings its own Nix libraries, about 170 MiB with what it shares with Nix. The editor needs it for anything beyond highlighting.
- **Completion's first use costs time and memory.** nixd evaluates the pinned nixpkgs, as the Software Center's search index build does.
- **The guide is ours to keep current.** When Recipes' templates change, the TulsiOS entries and their examples change with them, and `checks.nix-guide` catches examples that no longer parse or pass.
- **The Assistant is still the way for larger work.** The editor helps with the last step a Recipe could not take; it doesn't package software from nothing.
- **Hand-written files** outside drafts (any `.nix`) get completion, problems and the guide, but no Build or Install. Installing still goes through local packages.
