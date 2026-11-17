# Ocimum Assistant

A chat window (menu: **Assistant**) where you ask for changes in plain language:
*"install a lightweight video player"*, *"turn on printing"*, *"what did I change
recently?"*. It answers with Claude, and its only tools are those of
[tulsi-mcp](MCP.md). Every change can be undone.

**What asks first** (ADR 0014; with Starah, at the default level 2):
- **Goes ahead on its own:** changes that a restart into the previous system fully
  undoes, such as installing software, turning features on or off, and browser
  extensions.
- **Asks you first,** in Starah's Agent Request window: changes a rollback cannot undo,
  such as accounts, boot, disks, scripts, and software the Assistant packaged itself.
- You can change this in Starah's Agent Privileges: level 1 asks about everything.

**Receipts.** Under each reply, a line shows what actually changed, taken from tulsi-mcp's
receipts rather than from the model's words, and who approved it. It has an **Undo**
button.
- If a reply says something changed but nothing did, a note says so.
- **Recent changes** (clock icon) opens the Software Center's History page.

## Setup

1. Get an API key at [platform.claude.com](https://platform.claude.com).
2. Open the Assistant → Settings (gear) → paste the key → Save. It is stored in your
   keyring (GNOME Keyring), not in a file.

Without a stored key, the `ANTHROPIC_API_KEY` environment variable or an
`ant auth login` profile is used.

Settings:

| Setting | Default | Notes |
|---|---|---|
| Model | Claude Opus 5.5 | Sonnet 5.5 is faster, Haiku 5.5 fastest and cheapest |
| Thoroughness | Medium | `low` / `medium` / `high`: how much the model thinks before acting |

Stored in `~/.config/ocimum-assistant/settings.json`.

## How it works

- `apps/ocimum-assistant`: Python + GTK 3, so it runs on GTK3-O.
- It starts `tulsi-mcp` as a subprocess and gives the model its tools. The agent loop
  (`agent.py`) runs a model turn, executes the tool calls through tulsi-mcp, returns the
  results, and repeats until the model answers. That is at most 25 steps per request,
  and **Stop** ends it after the current step.
- Claude requests (`providers.py`) stream the answer and a summarized view of the
  model's thinking (shown in the status line). Tool inputs stream as they are written.
  Prompt caching is automatic: the system prompt and tool list stay fixed per
  conversation. Server-side refusal fallbacks are on: if a request is declined for
  policy reasons, the API retries it on a suitable model.
- Tool inputs cut off by the output limit are never run. Unreadable tool calls are
  retried. Refusals and API errors are explained in the window (a rejected key opens
  Settings).
- Providers are pluggable (`agent.Provider`). `OCIMUM_ASSISTANT_PROVIDER=fake:script.json`
  replays a scripted conversation; tests use it.

## Privacy

Your requests, and whatever the tools return (package lists, `configuration.nix`,
history), are sent to the Anthropic API. Nothing else on the system is readable by the
model: it has no shell and no file access beyond tulsi-mcp's tools.
