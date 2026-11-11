# ADR 0001: Flake distribution on top of nixpkgs, not a nixpkgs fork

Status: accepted (2026-11-11)

## Context
Hard-forking nixpkgs (~120k packages) means a huge maintenance burden: constant merges, rebuilding the binary cache ourselves, and security lag.

## Decision
TulsiOS is a flake that pins upstream nixpkgs as an input and adds its own overlay (`nix/overlays`), NixOS modules (`nix/modules`) and packages. Individual components (for example Cinnamon) are forked as separate source trees and swapped in through the overlay.

## Consequences
Users get the official binary cache for everything we do not change. Upstream updates mean bumping `flake.lock`. If a nixpkgs patch is ever required, it goes into a small `nixpkgs` fork branch used only as the flake input, never a long-lived divergence.
