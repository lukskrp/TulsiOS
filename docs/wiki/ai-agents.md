# AI agents and Starah

TulsiOS lets AI coding agents (Claude Code, Codex, Gemini CLI, OpenCode, Antigravity,
Aider, …) work on your computer without handing them your whole account. **Starah**
decides what each agent may do. You set it in **Agent Privileges** (in the app menu, or
`starah-session --show`).

## What an agent may change on the system

Every agent has a **level**, chosen by you:

| Level | What the agent does on its own |
| --- | --- |
| 0 Observe | Looks, changes nothing |
| 1 Propose | Nothing: you approve every change (the default for coding agents) |
| 2 Routine | Changes a restart into the previous system undoes: installing software, turning features on or off |
| 3 Administer | Also edits the system configuration and manages services |
| 4 Delegate | Everything an administrator can, except Starah, accounts and passwords |

When a change needs you, the **Agent Request** window opens: it shows what will change.
Reject is the default. Every change, approved or not, can be undone in the Software
Center's History.

## What an agent may see of your files

Agents installed through TulsiOS (the Software Center's **AI Agents** page, or
`tulsi install`) start as **their own account**, not as you, when you run them in a
terminal:

- They see **only the folder you start them in**. Start them in your project:
  `cd ~/code/my-project && claude`. They can't be started in your home folder
  itself.
- What they write there stays **yours**: same owner, same permissions.
- They have **their own home**, with their own logins and settings, separate for every
  person on the computer. The first time, each agent asks you to log in.
- Only your terminal's look and language settings and model API keys
  (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, …) are passed on to them.
- When you close the terminal, the agent stops.

Because they are not you, they **can't**:

- push with git or sign commits (your SSH keys and `~/.gitconfig` aren't there);
- read your other projects, browser data, documents or passwords.

### Letting an agent use your whole home

If you trust an agent, Agent Privileges has, under each agent, **May use my whole home
folder**. Turning it on asks for your password. The agent then works with your whole
home folder: your logins and settings, your SSH keys (it can `git push`), your other
projects. Its changes to the system still follow its level. Turn it off at any time;
it applies from the agent's next start. In a terminal: `starah home claude on`
(or `off`).

## ⚠ Agents installed outside TulsiOS

Starah starts an agent under its own account only if TulsiOS installed it. An agent you
installed some other way **runs as you**, with access to all your files:

- with `npm install -g`, `pip`, `curl … | sh`, or a downloaded program;
- run with `npx`, from an editor plugin, or by its full path;
- an agent that is not in the Software Center's list.

TulsiOS still recognises many agents when they try to change the system (Claude Code,
Codex, Gemini CLI, Qwen Code, Crush, Goose, and any agent that follows TulsiOS' agent
instructions), so those changes still go through Starah. But **nothing stops such an
agent from reading or changing your files**.

To be safe, install agents from the Software Center's **AI Agents** page. To check how
an agent runs, ask it to run `id -un`: under Starah the answer is `starah-NAME`, not
your user name.

## Also good to know

- Agents can reach the internet: they need it for their models.
- An agent you run without a terminal (from a script or an editor) runs as you; its
  system changes still go through Starah.
- Starah keeps a record of what agents did: `starah audit`.
- Local models (Ollama, llama.cpp) and what your computer can run: the Software Center's
  AI Agents page, **Check What My Computer Can Run**.
