# Editing files

TulsiOS's text editor for terminals is **Fresh**. When a program opens an editor for
you, it is Fresh: `git commit`, `crontab -e` and `sudoedit`.
You can also open it from the app menu, or type `fresh FILE` in a terminal.

Fresh works like a desktop app:

| Keys | What they do |
| --- | --- |
| **Ctrl+S** | Save |
| **Ctrl+Q** | Quit (it asks about unsaved changes) |
| **Ctrl+Z**, **Ctrl+Y** | Undo, redo |
| **Ctrl+F** | Find |
| **Ctrl+P** | Quick open: files and commands, searchable |

The mouse and the menus work too.

## System files

To change a file that belongs to the system, such as one in `/etc`, use **sudoedit**:

```sh
sudoedit /etc/FILE
```

It asks for your password, opens a copy in Fresh as you, and when you close it, writes
the file back. Don't run an editor itself with `sudo`: your settings don't come along.

The system's own settings (`/etc/nixos/configuration.nix`) are changed with
`tulsi config`, so each change is recorded and can be undone:

```sh
tulsi config show > ~/configuration.nix
fresh ~/configuration.nix
tulsi config apply ~/configuration.nix --summary "what I changed"
```

## Another editor

Install it (for example `tulsi install nano`), and set it as yours in `~/.profile`:
`export EDITOR=nano VISUAL=nano`. Double-clicked text files open the desktop's own
editor (Xed on Ocimum).
