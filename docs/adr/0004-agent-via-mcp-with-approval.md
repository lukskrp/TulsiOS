# ADR 0004: Agents act through MCP tools with mandatory human approval

Status: accepted (2026-11-11)

## Context
An LLM agent that edits system configuration as root is a risk: hallucinated options, destructive changes, prompt injection from web content.

## Decision
System actions are exposed only through `tulsi-mcp` (an MCP server over tulsid). Agents can read state and *propose* changes. `apply` always requires interactive approval of a shown diff (polkit). Free-form Nix edits must parse, format and pass `dry-build` before they are offered. The LLM provider is pluggable (Claude API default).

## Consequences
Every agent change is reviewable and reversible (git + NixOS generations). Third-party agents can drive TulsiOS through the same tools. Fully autonomous operation is deliberately not supported.
