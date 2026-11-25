# tulsi.agentGating: coding agents a person starts in a terminal run as their
# own Starah accounts (ADR 0026).
#
# - Each agent CLI installed through TulsiOS (state.json) is declared to Starah
#   (plus a fallback for agents TulsiOS doesn't know). People see them in Starah
#   Setup and Agent Privileges; each starts at `level` (1: asks about every change).
# - Its command (`claude`, `codex`, …) is wrapped: started in a terminal, it runs
#   as `starah run --interactive --agent NAME`, as its own user, in the project
#   folder it was started in (or the person's whole home, if they allowed that
#   agent in Agent Privileges), with its own logins and TulsiOS' skills.
# - Started any other way, `tulsi` and `tulsi-mcp` still recognise it by the
#   environment variables it sets (data/agent-clis.json) and make its system
#   changes as its Starah account.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.tulsi.agentGating;
  table = lib.importJSON ../../data/agent-clis.json;
  installed =
    if config.tulsi.state.enable then (lib.importJSON config.tulsi.state.file).packages or [ ] else [ ];
  wanted = lib.filter (a: lib.elem a.attr installed || lib.elem a.name cfg.extraAgents) table.agents;
  byName = lib.listToAttrs (map (a: lib.nameValuePair a.name a) table.agents);

  # TulsiOS' skills and AGENTS.md in each agent's own home (tulsi.agentSkills
  # links them into people's homes; an agent under Starah has its own).
  skills = "/etc/tulsi/agents/skills";
  instructions = "/etc/tulsi/agents/AGENTS.md";
  homeLinks =
    name:
    lib.optionalAttrs config.tulsi.agentSkills.enable (
      {
        ".agents/skills" = skills;
        ".agents/AGENTS.md" = instructions;
      }
      // {
        claude = {
          ".claude/skills" = skills;
          ".claude/CLAUDE.md" = instructions;
        };
        codex = {
          ".codex/skills" = skills;
          ".codex/AGENTS.md" = instructions;
        };
        gemini = {
          ".gemini/config/skills" = skills;
          ".gemini/GEMINI.md" = instructions;
        };
        opencode.".config/opencode/AGENTS.md" = instructions;
        qwen.".qwen/AGENTS.md" = instructions;
      }
      .${name} or { }
    );

  agent = name: description: {
    level = lib.mkDefault cfg.level;
    inherit description;
    homeLinks = homeLinks name;
  };

  # `claude` → `starah run --interactive --agent claude -- <the real claude>`.
  wrapper =
    name: package:
    let
      real = lib.getExe package;
      title = (byName.${name} or { title = name; }).title;
    in
    lib.hiPrio (
      pkgs.writeShellScriptBin package.meta.mainProgram ''
        # ${title}, started as its own Starah account (TulsiOS, ADR 0026).
        if [ -n "''${STARAH_AGENT:-}" ]; then
          exec ${real} "$@"
        fi
        if [ -t 0 ] && [ -t 1 ]; then
          exec /run/current-system/sw/bin/starah run --interactive --agent ${name} -- ${real} "$@"
        fi
        # No terminal (a script, an editor): it runs as the person, and its system
        # changes still go through Starah (tulsi recognises TULSI_AGENT).
        TULSI_AGENT=${name} exec ${real} "$@"
      ''
    );
in
{
  options.tulsi.agentGating = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = config.services.starah.enable && config.tulsi.daemon.enable;
      defaultText = lib.literalExpression "config.services.starah.enable && config.tulsi.daemon.enable";
      description = ''
        Run coding agents started in a terminal (Claude Code, Codex, Gemini CLI, …)
        as their own Starah accounts, so the level the person chose for each
        decides, and they see only the project folder they were started in.
      '';
    };
    level = lib.mkOption {
      type = lib.types.ints.between 0 4;
      default = 1;
      description = "Each agent's level until the person chooses one (1: asks about every change).";
    };
    extraAgents = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      example = [ "claude" ];
      description = ''
        Agents from data/agent-clis.json to declare even when their package was
        not installed through TulsiOS.
      '';
    };
    packages = lib.mkOption {
      type = lib.types.attrsOf lib.types.package;
      default = lib.listToAttrs (
        map (a: lib.nameValuePair a.name pkgs.${a.attr}) (
          lib.filter (a: lib.elem a.attr installed) table.agents
        )
      );
      defaultText = lib.literalMD "the agent CLIs installed through TulsiOS";
      description = ''
        Agent name → package whose main program is wrapped to start under Starah.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    services.starah.agents =
      lib.listToAttrs (
        map (a: lib.nameValuePair a.name (agent a.name "${a.title}, started in a terminal")) wanted
      )
      // lib.mapAttrs (name: _: agent name "${name}, started in a terminal") (
        lib.removeAttrs cfg.packages (map (a: a.name) wanted)
      )
      // {
        ${table.fallback} = agent table.fallback "Other coding agents started in a terminal";
      };

    environment.systemPackages = lib.mapAttrsToList wrapper cfg.packages;

    warnings = lib.optional config.tulsi.daemon.wheelNoPassword ''
      tulsi.daemon.wheelNoPassword is on: a coding agent a person starts in a terminal can
      change the system without anyone being asked, unless TulsiOS recognises it (ADR 0026).
    '';
  };
}
