# ADR 0006: GTK3-O is ABI-stable and grafted system-wide

Status: accepted (2026-11-11)

## Context
GTK3-O (`github.com/lukskrp/GTK3-24-Fork-Imprv`, branch `gtk-3-24`, to be renamed
GTK3-O) is the Ocimum fork of GTK 3.24. Replacing nixpkgs' `gtk3` through an overlay
would change the hash of thousands of packages (Firefox, LibreOffice, GIMP…). They
would all need compiling locally, with no official binary cache.

## Decision
- **GTK3-O keeps the GTK 3.24 ABI.** It may add features and change internals. It may not
  remove or change exported symbols, public struct layouts, function signatures or
  enum values. ABI-breaking, GTK 4-like work goes into a separate future hard fork,
  **OTK**.
- Everything is built against stock nixpkgs `gtk3`. The `ocimum.gtk3o` module
  (default on with `ocimum.desktop`) sets
  `system.replaceDependencies.replacements = [{ oldDependency = gtk3; newDependency = gtk3-o; }]`.
  This rewrites references in the finished system, so every GTK 3 program loads GTK3-O.
- `nix/packages/gtk3-o.nix` overrides only `src`. Name and version stay equal to
  stock gtk3, because the graft rewrites store paths in place and needs equal
  lengths.
- `checks.gtk3-o-abi` (`gtk3-o.abiCheck`) fails if GTK3-O stops exporting any symbol
  that stock gtk3 exports, for libgtk-3, libgdk-3 and libgailutil-3.

## Consequences
- No mass compiling; the binary cache keeps working. Every GTK 3 app is consistent:
  one libgtk-3 per process (verified by `checks.software-center`).
- Disk cost: GTK apps in the closure get rewritten copies in the store. Rebuilds
  take somewhat longer when new GTK apps are added (the graft uses import-from-derivation).
- The symbol check catches removed symbols, not changed struct layouts or semantics.
  Those rely on review discipline in GTK3-O.
- OTK, being ABI-breaking, will need a different approach: rebuilding dependents
  plus our own binary cache. That is out of scope until mass compiling is affordable.
