# ADR 0002: A JSON state file is the contract between tools and Nix

Status: accepted (2026-11-11)

## Context
GUIs, the browser bridge and an LLM agent all need to change the system. Generating or rewriting arbitrary Nix code from each of them is fragile and hard to validate.

## Decision
All machine-made changes go into one schema-validated file, `state.json` (`state/schema.json`, `crates/tulsi-state`). The `tulsi.state` NixOS module converts it to NixOS options. The Nix store is never modified directly.

## Consequences
Edits are trivial to make, diff, validate and undo. Users can still hand-write Nix next to it. The schema must grow carefully and be versioned (`version` field). Free-form Nix editing (agent only) is a separate, stricter path (see ADR 0004).
