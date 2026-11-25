# ADR 0023: AI onboarding

Status: accepted (2026-11-25).

## Context

People come to TulsiOS wanting to use LLM agents, from the cloud or on their own
machine, and had no place to start:

- **Agent CLIs had no place of their own.** They were ordinary rows in the
  package index (ADR 0012), with no category; the Software Center had no
  category pages, only search.
- **Nobody could say whether a local model would run.** TulsiOS had no
  hardware detection and no local runner on offer.

Omarchy (github.com/omacom/omarchy) offers a keyboard menu of agents that
installs them with mise. TulsiOS can't do that: mise installs outside Nix, so
those installs would be neither recorded nor undoable.

## Decision

- **A curated list, as data.** `ocimum_software_center/ai-agents.json` names
  the packages in three sections:
  - coding agents in the terminal: OpenCode, Claude Code, Codex, Gemini CLI,
    Qwen Code, Aider, Goose, Crush, Antigravity CLI (agy), GitHub Copilot CLI,
    Amp, Cursor CLI;
  - agent IDEs: Antigravity, Antigravity Hub;
  - local runners: Ollama (with its CUDA, ROCm and Vulkan builds) and llama.cpp.

  Each entry has a name, vendor, homepage, a one-line description, and what it
  needs (an account, an API key, memory). Changing the list means editing JSON,
  not code.
- **The Software Center's "AI Agents" page** shows the list with the usual
  package rows. Installs go through tulsid like any other: confirmation,
  generation, undo. Unfree agents ask for their licence first
  (`tulsi.daemon.unfreeAgents` now also lists Antigravity's three packages).
  `ocimum-software-center --page ai` (the `show-page` action) opens the page,
  in the running instance if there is one.
- **`checks.ai-agents-index`** fails the build when a listed package isn't in
  the package index, or is unfree and missing from `unfreeAgents`. Upstream
  renames are caught there, not as a dead Install button. Antigravity's
  `antigravity` attr was an alias, which the index leaves out, and this check
  is how that was found.
- **`tulsi-ai-check`: advice by size class, not by model name.**
  - It reads the processor (cores, AVX2/AVX-512), memory, disk and graphics
    cards from `/proc` and `/sys`, plus `nvidia-smi` when NVIDIA's driver is
    there. AMD cards report their memory in sysfs; Intel and small-carve-out AMD
    GPUs count as integrated.
  - It estimates a 4-bit model at 0.6 GB per billion parameters plus 1.5 GB,
    against 90% of the card's memory and 70% of RAM. That gives five classes
    (≤3B, 7–8B, 12–14B, 27–32B, 70B+), each marked as fitting on the card, on
    card plus processor, on the processor, or not at all, with a rough speed.
  - Example models per class live in `ai-models.json`, dated ("as of"),
    because they go out of date within months; the arithmetic stays valid. The
    output says so.
  - It recommends the Ollama build for the card (`ollama-cuda`, `ollama-rocm`,
    `ollama-vulkan`), and the page installs that build in place of plain
    `ollama`.
  - The result is cached in `~/.cache/tulsi/ai-check.json`; the page shows it.
- **`tulsi-terminal [--hold] -- CMD`** runs a command in the desktop's own
  terminal: GNOME Terminal on Ocimum, Konsole on SonicDE, st on dwm. The page's
  "Check What My Computer Can Run…" button and the launcher's "Check My
  Hardware" action use it.
- **A launcher on every desktop:** `org.tulsi.AIAgents.desktop`, with its own
  icon.
  - Every app menu has it.
  - **Ocimum:** on the desktop, below Starah's, through
    `ocimum.desktop.topRightLaunchers`. The script that places these now keeps
    a list of the launchers it has placed (`~/.local/state/ocimum/desktop-launchers`).
    A launcher added in a later release therefore reaches existing users once,
    and one a person deleted is never put back.
  - **SonicDE** has no desktop icons, so it is a pinned panel app.
  - **dwm:** Super+Shift+A, since Super+I is dwm's own key.
- **Its name is translated** through the gettext set-up in ADR 0024.

## Consequences

- The agent list and the example models need occasional edits: new agents, new
  open models. The index check covers the agent list; the model examples are
  advice only.
- The size classes are rules of thumb. Mixture-of-experts models,
  long contexts and other quantisations shift the numbers. The output
  says it gives rough pointers.
- Ollama is installed as a package, not as a service. People start it with
  `ollama serve`. Turning on `services.ollama` from the page is possible later
  (the Software Center already enables services).

## Verification

- Unit tests (`tests/test_ai.py`) on fake `/proc` and `/sys` trees cover:
  - a CPU-only laptop;
  - an AMD card with its memory read from sysfs;
  - an AMD APU;
  - an NVIDIA card read through `nvidia-smi`;
  - a machine too small for any model;
  - the agent list itself.
- `checks.ai-agents-index`.
- `checks.software-center`: `--page ai` hands over to the running app;
  `tulsi-ai-check --json` runs.
- `checks.ocimum-desktop`: the launcher is on the desktop, below Starah's.
- `checks.dwm-session`: Super+Shift+A, and the check opens in st through
  `tulsi-terminal`.
- `checks.sonic-desktop`: the panel pin.
