# tulsi.agentSkills: TulsiOS knowledge for coding agents (ADR 0022). Skills
# (SKILL.md, the Agent Skills format) and one AGENTS.md are installed under
# /etc/tulsi/agents and linked into each coding-agent CLI's folders at login, so
# Claude Code, Codex, Gemini CLI, OpenCode and the rest know how to change a
# TulsiOS system (through `tulsi`, never /etc/nixos). The idea is Omarchy's
# (github.com/omacom/omarchy, omarchy-agent-skills-link, MIT).
#
# A person's own files always win: AGENTS.md is linked only where there is no
# file, and only links that point into /etc/tulsi/agents are ever changed.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.tulsi.agentSkills;
  root = "/etc/tulsi/agents";

  link = pkgs.writeShellApplication {
    name = "tulsi-agent-skills-link";
    runtimeInputs = [ pkgs.coreutils ];
    text = ''
      # Link TulsiOS' agent skills and AGENTS.md into each coding agent's folders.
      root=${root}
      ours() { [[ -L $1 && $(readlink "$1") == "$root"/* ]]; }

      # Skills: ~/.agents/skills always (several CLIs read it), the others only
      # for agents that have been used (their folder exists).
      skill_dirs=("$HOME/.agents/skills")
      for d in .claude .codex .gemini/config .pi/agent; do
        [[ -d $HOME/$d ]] && skill_dirs+=("$HOME/$d/skills")
      done
      for dir in "''${skill_dirs[@]}"; do
        mkdir -p "$dir"
        # Drop our links to skills TulsiOS no longer ships.
        for l in "$dir"/*; do
          if ours "$l" && [[ ! -e $l ]]; then rm -f "$l"; fi
        done
        for skill in "$root"/skills/*/; do
          name=$(basename "$skill")
          target="$dir/$name"
          if [[ ! -e $target && ! -L $target ]] || ours "$target"; then
            ln -sfn "$root/skills/$name" "$target"
          fi
        done
      done

      # AGENTS.md where each CLI reads its global instructions, if there is no file.
      declare -A instructions=(
        [agents]="$HOME/.agents/AGENTS.md"
        [claude]="$HOME/.claude/CLAUDE.md"
        [codex]="$HOME/.codex/AGENTS.md"
        [gemini]="$HOME/.gemini/GEMINI.md"
        [opencode]="''${XDG_CONFIG_HOME:-$HOME/.config}/opencode/AGENTS.md"
        [qwen]="$HOME/.qwen/AGENTS.md"
      )
      for agent in "''${!instructions[@]}"; do
        file=''${instructions[$agent]}
        [[ $agent == agents || -d $(dirname "$file") ]] || continue
        mkdir -p "$(dirname "$file")"
        if [[ ! -e $file && ! -L $file ]] || ours "$file"; then
          ln -sfn "$root/AGENTS.md" "$file"
        fi
      done
    '';
  };
in
{
  options.tulsi.agentSkills = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = config.ocimum.desktop.enable || config.sonic.desktop.enable || config.tulsi.dwm.enable;
      defaultText = lib.literalExpression "config.ocimum.desktop.enable || config.sonic.desktop.enable || config.tulsi.dwm.enable";
      description = "TulsiOS skills and AGENTS.md for coding-agent CLIs, linked at login.";
    };
  };

  config = lib.mkIf cfg.enable {
    environment.etc."tulsi/agents".source = ../../agents;
    environment.systemPackages = [ link ];
    systemd.user.services.tulsi-agent-skills-link = {
      description = "Link TulsiOS agent skills into coding-agent CLIs";
      wantedBy = [ "default.target" ];
      serviceConfig = {
        Type = "oneshot";
        ExecStart = lib.getExe link;
      };
    };
  };
}
