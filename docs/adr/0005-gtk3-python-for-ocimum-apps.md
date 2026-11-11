# ADR 0005: Ocimum GUI apps use GTK 3 (GTK3-O) and Python

Status: accepted (2026-11-11). Supersedes the GTK4/libadwaita/relm4 plan in ADR-era docs.

## Context
Ocimum Desktop is a Cinnamon fork. Its toolkit base is **GTK3-O**, the project's own
fork of GTK 3.24. GUI apps (Software Center, later the Assistant window and settings
tools) should look and behave like the rest of the desktop and pick up GTK3-O
improvements, such as the file chooser's "New Folder" item.

GTK 4 + libadwaita was the original plan. libadwaita ignores GTK themes, which
conflicts with Cinnamon theming. The Rust bindings for GTK 3 (`gtk3-rs`) were
archived in 2024, and relm4 is GTK 4 only.

## Decision
- GUI apps are written in **Python with PyGObject on GTK 3** (optionally libxapp
  widgets), like Linux Mint's own tools (mintinstall, Cinnamon settings).
- They talk to `tulsid` over D-Bus with `Gio.DBusProxy`; they never touch Nix or
  state.json directly.
- Logic that can be tested without a display lives in GTK-free modules (e.g.
  `apps/ocimum-software-center/ocimum_software_center/model.py`) with pytest tests.
- The daemon, CLI and MCP server stay in Rust.

## Consequences
- Apps follow the Ocimum (Cinnamon) theme and get GTK3-O changes automatically.
- What GTK 3 lacks compared to GTK 4: recycling list views (we cap result lists
  at a few hundred rows), GPU rendering and native fractional scaling. Fractional
  scaling is a good candidate for GTK3-O improvements.
- Python is slower than Rust, but fast enough for these apps.
