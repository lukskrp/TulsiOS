---
name: tulsios-diagnose-crash
description: >
  Find out why a program crashed or failed to start on TulsiOS and fix it the
  TulsiOS way: core dumps (coredumpctl), the journal, a package's missing
  libraries or wrapper, and whether a recent change (tulsi history) caused it.
  Triggers: crashed, segfault, core dumped, won't start, closes right away.
---

# Diagnosing a crash on TulsiOS

1. **Find the crash.** `coredumpctl list --since today` (newest last), then
   `coredumpctl info PID` for the signal, executable and stack. If there is no
   core dump, run the program from a terminal and read what it prints.
2. **Read the journal around it.** `journalctl --user -b --since "10 min ago"`
   for desktop programs, `journalctl -b -u NAME` for services.
3. **Did a change cause it?** `tulsi history` lists recent changes. If the crash
   started after one, `tulsi undo ID` takes back that change alone (it asks for
   authorization); say which change you suspect and why before undoing.
4. **Common TulsiOS causes:**
   - A downloaded program (not a TulsiOS package) that wants libraries from
     `/usr/lib`: there are none on NixOS. Package it instead: `tulsi recipe plan
     FILE` (the `tulsios` skill), which wraps it with what it needs.
   - "cannot open display" or D-Bus errors from a terminal outside the session:
     run it from the desktop's own terminal.
   - Debugging tools are a command away without installing them:
     `nix shell nixpkgs#gdb nixpkgs#strace`, then `strace -f PROGRAM` or
     `gdb -p PID`.
   - A GTK 3 program drawing wrongly: TulsiOS runs every GTK 3 program on GTK3-O
     (an ABI-compatible GTK 3 fork). Note it in the report; the theme can be
     switched back with `tulsi-theme undo` to rule a theme out.
5. **Report**: what crashed, the evidence (signal, the journal lines), the cause
   you found or suspect, and what you changed. Do not change the system to
   "try things"; every change goes through `tulsi`, and the person approves it.
