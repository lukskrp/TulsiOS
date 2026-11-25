# Agent skills (ADR 0022): at login, TulsiOS' skills and AGENTS.md are linked into
# the coding-agent CLIs a person has used, and their own instruction files are
# never replaced.
{ self }:
{
  name = "agent-skills";

  nodes.machine =
    { modulesPath, ... }:
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      tulsi.agentSkills.enable = true;
    };

  testScript = ''
    machine.wait_for_unit("multi-user.target")

    def alice(command):
        return machine.succeed(f"su - alice -c '{command}'")

    with subtest("the skills are installed"):
        for skill in ["tulsios", "tulsios-make-theme", "tulsios-diagnose-crash"]:
            machine.succeed(f"grep -q '^name: {skill}$' /etc/tulsi/agents/skills/{skill}/SKILL.md")
        machine.succeed("grep -q 'tulsi install' /etc/tulsi/agents/AGENTS.md")

    with subtest("a person's own instructions stay; the rest is linked"):
        # Claude Code and Codex have been used; alice wrote her own CLAUDE.md.
        alice("mkdir -p ~/.claude ~/.codex && echo mine > ~/.claude/CLAUDE.md")
        # The user unit runs at login; run it now as the login would.
        machine.succeed("loginctl enable-linger alice")
        machine.wait_until_succeeds("systemctl --user -M alice@ is-active default.target")
        machine.succeed("systemctl --user -M alice@ start tulsi-agent-skills-link.service")
        assert alice("cat ~/.claude/CLAUDE.md").strip() == "mine"
        assert alice("readlink ~/.codex/AGENTS.md").strip() == "/etc/tulsi/agents/AGENTS.md"
        assert alice("readlink ~/.agents/AGENTS.md").strip() == "/etc/tulsi/agents/AGENTS.md"
        for d in ["~/.agents/skills", "~/.claude/skills", "~/.codex/skills"]:
            alice(f"test -f {d}/tulsios/SKILL.md")
        # Agents never used get nothing.
        alice("test ! -e ~/.gemini")

    with subtest("their own skill of the same name stays, and a rerun changes nothing"):
        alice("rm ~/.codex/skills/tulsios && mkdir ~/.codex/skills/tulsios && echo own > ~/.codex/skills/tulsios/SKILL.md")
        alice("tulsi-agent-skills-link && tulsi-agent-skills-link")
        assert alice("cat ~/.codex/skills/tulsios/SKILL.md").strip() == "own"
        assert alice("cat ~/.claude/CLAUDE.md").strip() == "mine"
        alice("test -L ~/.claude/skills/tulsios-make-theme")
  '';
}
