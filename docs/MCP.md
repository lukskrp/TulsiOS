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
| `history` | no | Recent changes: id, summary, and who made them (a person or an agent) |
| `plan_change` | no | What a list of operations would change |
| `propose_configuration_edit` | no | Syntax-check new `configuration.nix` contents and show the diff |
| `apply_change` | **yes, after approval** | Packages, browser extensions, service toggles |
| `apply_configuration_edit` | **yes, after approval** | Replace `configuration.nix` (complete contents) |
| `undo_last_change` | **yes, after approval** | Revert the most recent change |
| `undo_change` | **yes, after approval** | Take back an older change by its id from `history`; later changes stay (ADR 0015) |
| `fetch_source` | no | Download a URL (or take a file already in the store) and describe it: kind, hash, contents, build hints |
| `build_package` | no | Save a `callPackage` expression as a draft and build it in Nix's sandbox |
| `try_package` | no | Run a program of the last build briefly (empty home, no display) |
| `propose_local_package` | **yes, after approval** | Add the built package to this computer as a local package (ADR 0013) |
| `list_themes` | no | The desktop themes (palettes) the person can switch to (ADR 0021) |
| `set_theme` | the person's own setting, no approval | Switch their desktop's colours and background; only in their own desktop session |
| `undo_theme` | the person's own setting, no approval | Back to the theme before (or the desktop's own look) |

Operations use the `state.json` format, e.g. `{"op":"addPackage","name":"vlc"}`
(see `crates/tulsi-state/src/ops.rs`).

## Packaging software nobody packaged

When nothing in nixpkgs fits, an agent can package the software itself. This is what
the Assistant does from the "Install the TulsiOS Way" window (ADR 0013).
1. `fetch_source` fetches and inspects it.
2. `build_package` builds a `callPackage` expression against the system's pinned
   nixpkgs (`/etc/tulsi/nixpkgs`).
3. `try_package` runs the result.
4. `propose_local_package` asks you, showing the whole expression.

Approved packages live in `/etc/nixos/tulsi/pkgs/<name>/` and in `localPackages` in
state.json. They appear in the Software Center under "Made on this computer", and
`tulsi undo` removes them. Expressions that read host files, fetch without a hash or
weaken the build sandbox are refused before they are built or applied.

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

## Receipts

Every change tool (`apply_change`, `apply_configuration_edit`, `undo_last_change`,
`propose_local_package`) returns a receipt in `structuredContent.receipt`. It records
what actually happened, so clients don't have to trust the model's summary:

```json
{ "tool": "apply_change", "outcome": "applied", "approved_via": "Starah (the agent's level)",
  "action": "org.tulsi.apply", "changes": ["+ package vlc"], "commit": "abc1234", "detail": "…" }
```

`outcome` is one of:
- `applied`;
- `nothing` (the system already matched);
- `rolled_back` (the rebuild failed);
- `rejected` (not approved, with the reason in `detail`).

## What approval does and does not protect

Approval guarantees that changes made **through tulsi-mcp** were seen and accepted by
you. It does not sandbox the agent. An agent that can also run shell commands could
run `tulsi` or `sudo` directly, and then only polkit (password prompts) stands in the
way. For an agent you do not fully trust, give it tulsi-mcp but no shell. The polkit
defaults (`auth_admin_keep`) still apply to everything tulsid does.

**With Starah** (ADR 0011, on by default on the Ocimum Desktop), the agent is not you.
- **How tulsi-mcp runs.** The Assistant starts it as the Starah agent `assistant`:
  `starah run --agent assistant -- tulsi-mcp --approval starah`. It runs under its own
  account in a sandbox, where `sudo`, `su` and `pkexec` don't work and the system and home
  directories can't be touched.
- **Who decides.** Starah answers every polkit question about that account, including
  tulsid's, from the level you chose. tulsid uses two actions (ADR 0014):
  - `org.tulsi.apply` for changes a NixOS rollback fully undoes: packages, services,
    browser extensions, and configuration edits that only touch allow-listed settings;
  - `org.tulsi.configure` for everything else: accounts, boot, file systems, scripts,
    unknown settings, and local packages the agent wrote.
  - At level 1 (Propose) each change appears in Starah's **Agent Request** window with the
    same description, reason and diff.
  - At level 2 (Routine, the Assistant's default) `apply` changes go ahead on their own;
    `configure` changes are asked, and the request says which settings make them so.
  - At level 3 (Administer) both go ahead on their own.
  - Everything is audited.
- **Undo needs what the change needed.** Every commit records its action
  (`Tulsi-Action:` trailer), so undoing an account change asks again.
- **A shell doesn't help.** Even an agent with a shell inside that sandbox gets only what
  its level allows.
