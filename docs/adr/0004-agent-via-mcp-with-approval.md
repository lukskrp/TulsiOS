# ADR 0004: Agents act through MCP tools with mandatory human approval

Status: accepted (2026-11-11), refined with the implementation in Phase 5.

## Context
An LLM agent that edits system configuration as root is a risk: hallucinated options,
destructive changes, prompt injection from web content.

## Decision
- System actions for agents are exposed through `tulsi-mcp` (`crates/tulsi-mcp`), an MCP
  server (stdio) over tulsid. It has read-only tools (search, inspect, plan, propose)
  and three change tools (`apply_change`, `apply_configuration_edit`,
  `undo_last_change`).
- Every change tool asks the human first. The approval request shows the requester, the
  agent's stated reason, the exact changes and the diff for configuration edits.
  Channels: the desktop dialog `ocimum-approve` (defaults to Reject), else MCP
  elicitation through the client, else **refuse**. There is no silent approval.
- tulsid validates before anyone is asked: package names, unfree packages, extension ids,
  and Nix syntax via `nix-instantiate --parse`. The rebuild is the full check. A failed
  rebuild rolls back automatically, and the agent receives the log.
- `configuration.nix` edits take the complete new file and run in the same transaction
  model as `state.json`: git history, rollback on failure, undo.
- The change from the original plan: the full check is the rebuild itself, with
  automatic rollback, instead of a separate format + `dry-build` step before approval.
  This keeps approval fast. A failed rebuild leaves the system unchanged.
- The LLM provider stays pluggable. tulsi-mcp is provider-neutral, and the Ocimum
  Assistant (next) uses Claude by default.

## Consequences
- Every agent change is reviewable and reversible (git + NixOS generations).
  Any MCP client (Claude Code, the Assistant, others) uses the same tools.
- Approval protects changes made *through tulsi-mcp*. It does not sandbox an agent that
  also has a shell; polkit still applies there. See docs/MCP.md.
- Fully autonomous operation is deliberately not supported.
