# tulsi-mcp: letting AI agents manage TulsiOS

`tulsi-mcp` is a [Model Context Protocol](https://modelcontextprotocol.io) server
(stdio transport). AI agents can use it to search packages, inspect the system and
propose changes. **Every change is shown to you for approval** before `tulsid` applies
it, and every applied change can be undone.

## Connect an agent

Claude Code:

```sh
claude mcp add tulsi -- tulsi-mcp
```

Any other MCP client: run `tulsi-mcp` as a stdio server, e.g.

```json
{ "mcpServers": { "tulsi": { "command": "tulsi-mcp" } } }
```

Then ask, for example: *"install a lightweight video player and enable printing"*.

## Tools

| Tool | Changes the system? | What it does |
|---|---|---|
| `search_packages` | no | Search ~137k nixpkgs packages; returns attribute names |
| `package_info` | no | Details of one package |
| `get_state` | no | Managed packages, browser extensions, service toggles |
| `read_configuration` | no | The user's `configuration.nix` |
| `history` | no | Recent changes |
| `plan_change` | no | What a list of operations would change |
| `propose_configuration_edit` | no | Syntax-check new `configuration.nix` contents and show the diff |
| `apply_change` | **yes, after approval** | Packages, browser extensions, service toggles |
| `apply_configuration_edit` | **yes, after approval** | Replace `configuration.nix` (complete contents) |
| `undo_last_change` | **yes, after approval** | Revert the most recent change |

Operations use the `state.json` format, e.g. `{"op":"addPackage","name":"vlc"}`
(see `crates/tulsi-state/src/ops.rs`).

## Approval

For each change you see who asked, the agent's stated reason, the exact changes, and
the diff for `configuration.nix` edits. You can approve or reject.

| Channel | When |
|---|---|
| Desktop dialog `ocimum-approve` | a graphical session is reachable (`DISPLAY`/`WAYLAND_DISPLAY`) and the Software Center is installed |
| MCP elicitation (your agent client asks you) | otherwise, if the client supports elicitation |
| Refused | neither is available: nothing is changed |

The dialog defaults to **Reject**, so pressing Enter never approves.
Force a channel with `--approval dialog|elicitation` (or `TULSI_MCP_APPROVAL`). Use
`--approver PROGRAM` for a custom approver: it reads the request as JSON on stdin and
exits 0 to approve or 1 to reject.

Before anyone is asked, `tulsid` validates everything: unknown package names ("did you
mean"), unfree packages, invalid extension ids, and Nix syntax errors. After approval,
the change is rebuilt. If the rebuild fails, it is rolled back automatically and the
agent gets the error log.

## What approval does and does not protect

Approval guarantees that changes made **through tulsi-mcp** were seen and accepted by
you. It does not sandbox the agent. An agent that can also run shell commands could
run `tulsi` or `sudo` directly, and then only polkit (password prompts) stands in the
way. For an agent you do not fully trust, give it tulsi-mcp but no shell. The polkit
defaults (`auth_admin_keep`) still apply to everything tulsid does.
