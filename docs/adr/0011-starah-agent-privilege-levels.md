# ADR 0011: Starah: levels of privilege for AI agents

Status: accepted (2026-11-14), prototype

## Context

TulsiOS lets AI agents change the system (ADR 0004), but until now:
- the agent ran as the human user;
- approval covered only changes made through tulsi-mcp (docs/MCP.md, "What approval
  does and does not protect");
- nothing was sandboxed.

The owner of a TulsiOS machine should be able to delegate privileges that are normally
gated by root to agents, choosing how much, and should be asked for anything beyond
that. TulsiOS asks this once at first login and shows the choice at later logins.

The question was whether this needs a modified kernel. It doesn't:
- **A distinct identity per agent:** the kernel already gives one, a UID, which it reports
  on every socket.
- **Decisions on privileged operations:** polkit already makes them for systemd, logind,
  NetworkManager, udisks, accounts and tulsid, and its rules can delegate a decision to a
  program.
- **Containment:** systemd's sandbox keeps an agent from getting around the decision
  (`NoNewPrivileges` stops setuid `sudo`/`su`/`pkexec`, and there are no capabilities and
  no writable system).

## Decision

Build **Starah** (Sanskrit "levels") as its own project, `lukskrp/starah`
(github.com/lukskrp/starah), and enable it on the Ocimum Desktop.
- **Agents:**
  - each agent is a system user `starah-<name>`;
  - it is started sandboxed by the broker `starahd` (`starah run`);
  - every polkit question about an agent account is answered by Starah's first, final
    rule, through `starah-polkit-check` → `starahd`.
- **Five levels:**
  - 0 Observe;
  - 1 Propose (everything is asked);
  - 2 Routine;
  - 3 Administer;
  - 4 Delegate (everything except the forbidden class: Starah itself, accounts and
    passwords, `pkexec`).
- **Classes:** polkit action ids are put in classes in a data file; unknown actions are
  "sensitive".
- **Asking:** "ask" files a request that the human answers in Starah's **Agent Request**
  window. An approval becomes a short-lived grant: one use for a described change, N
  minutes for a refused polkit action.
- **starah-session (OTK):**
  - **Starah Setup** at first login; saving needs the admin password;
  - an **Agent Privileges** summary at later logins and in the menu;
  - the request windows.
- **The Assistant:** its tulsi-mcp runs as agent `assistant`, level 1 by default, with
  `--approval starah`.

## Consequences

- An agent's power no longer depends on whether it has a shell: its sandbox and its
  level bound it, and everything it asks for is audited (`starah audit`).
- **Not covered:**
  - privileged operations that skip polkit (to be bounded later with Landlock or BPF-LSM
    rules per agent);
  - network policy;
  - programs the human runs as themselves.
- TulsiOS's flake gets the input `starah` (`github:lukskrp/starah`). To test local Starah
  changes: `--override-input starah path:$HOME/Starah`.
- The Ocimum Assistant needs `org.starah.run` to start its agent. Active local
  administrators have it without a prompt; other users are asked for an admin password.
