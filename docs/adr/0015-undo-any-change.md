# ADR 0015: Undo any change, in one History

Status: accepted (2026-11-17)

## Context

Until now only the latest change could be undone: tulsid's `Undo()`, the Software
Center's "Undo Latest Change" button, and the Assistant's Undo. That is a problem when
something earlier turns out to be wrong, for example a package the Assistant installed
yesterday, since everything after it would have to be undone first.

Changes come from people (the Software Center, `tulsi`) and from agents (the Assistant
through tulsi-mcp, under Starah). That raised the question of where to look at them.

## Decision

**One history, the system's, in the Software Center's History page.** It is not a
separate agent UI.
- **Each row shows** what changed, when, and **who**: "by alice", "by the Assistant", or
  "by agent x". It has its own **Undo** button.
- **The Assistant is the conversational way into the same feature.** "Undo the printer
  change from yesterday" uses the tulsi-mcp tools `history` and `undo_change`. Its clock
  button opens the History page.
- **Starah's windows stay about permissions** (what an agent may do), not about system
  history.

**How it works:**
- **Who.** tulsid records who asked as a `Tulsi-By: <user>` commit trailer (an agent is
  `starah-<name>`), next to `Tulsi-Action` (ADR 0014). `History()` returns both.
- **`UndoChange(commit)`** takes back any earlier change and keeps everything since. It is
  recorded as a new change, `tulsi: undo …`. `Undo()` is `UndoChange` of the latest.
  - **state.json is reverted by meaning, never by text** (`State::reverted`):
    - what that change added is removed;
    - what it removed is added back;
    - services it switched are switched back;
    - anything a later change already altered is left alone.
    - So it never conflicts.
  - **configuration.nix and local package files are merged three-way** (`git merge-file`):
    the change's own edit is reversed on top of the current file. If a later change edited
    the same lines, nothing is changed and the error names the file and asks to undo the
    later change first.
  - **Authorization** is the action that change needed (ADR 0014). So an agent undoing an
    old account edit still asks the human, and undoing an install doesn't.
- **`PlanUndo(commit)`** shows what it would change ("- package cowsay") or why it can't,
  before anyone confirms. The Software Center's confirm dialog, `tulsi undo [--dry-run]
  ID` and tulsi-mcp's approval request all use it.

## Consequences

- Any change can be taken back from the History page, by `tulsi undo <id>`, or by asking
  the Assistant.
- Changes recorded before this ADR have no `Tulsi-By`; they show without "by".
- Undoing interleaved `configuration.nix` edits can be refused. That is deliberate: a
  silent wrong merge of the system configuration is worse than asking for the later edit
  to be undone first.
