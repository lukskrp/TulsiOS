# ADR 0026: a coding agent started in a terminal (here: CLAUDECODE=1, as Claude
# Code sets for its commands) makes its changes as its own Starah account, and
# waits for the person when its level says so.
{ self }:
{
  name = "agent-gating";

  nodes.machine =
    { modulesPath, pkgs, ... }:
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      users.users.alice.extraGroups = [ "wheel" ];

      tulsi.state = {
        enable = true;
        file = ./state-test.json;
      };
      tulsi.daemon = {
        enable = true;
        rebuildCommand = [
          "${pkgs.writeShellScript "fake-rebuild" ''
            echo "rebuilding from $PWD"
          ''}"
        ];
      };
      services.starah = {
        enable = true;
        session.enable = false;
      };
      tulsi.agentGating.extraAgents = [ "claude" ];
      tulsi.agentSkills.enable = true;
      # A stand-in for Claude Code (the real one is unfree and large): what does it see?
      tulsi.agentGating.packages.claude = pkgs.writeShellScriptBin "claude" ''
        id -un; pwd; echo "HOME=$HOME"
        readlink "$HOME/.claude/skills"
        ls -A /home/alice
        echo made > made-by-claude
      '';
      # `su` shells are not active local sessions: let wheel steer Starah in the test.
      security.polkit.extraConfig = ''
        polkit.addRule(function(action, subject) {
          if (action.id.indexOf("org.starah.") == 0 && subject.isInGroup("wheel")) {
            return polkit.Result.YES;
          }
        });
      '';
      environment.systemPackages = [
        pkgs.git
        pkgs.jq
      ];
      # An MCP client's first message, as Claude Code would start tulsi-mcp.
      # Alice runs `claude` in her project, in a terminal (`script` gives it one).
      environment.etc."agent-test/claude.sh".source = pkgs.writeShellScript "claude-session" ''
        cd /home/alice/proj && exec script -qec claude /dev/null
      '';
      environment.etc."agent-test/mcp.sh".source = pkgs.writeShellScript "mcp" ''
        printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"1"}}}' \
          | CLAUDECODE=1 timeout 20 tulsi-mcp
      '';
    };

  testScript = ''
    state = "/etc/nixos/tulsi/state.json"

    def alice(cmd):
        return f"su - alice -c '{cmd}'"

    def requests():
        out = machine.succeed(alice("starah requests")).strip()
        return [line.split("\t") for line in out.splitlines() if line]

    def wait_request(word):
        machine.wait_until_succeeds(alice("starah requests") + f" | grep -q {word}", timeout=60)
        return requests()[-1][0]

    machine.wait_for_unit("tulsid.service")
    machine.wait_for_unit("starahd.service")
    machine.wait_for_unit("multi-user.target")

    with subtest("each agent CLI has its Starah account, and unknown ones a fallback"):
        status = machine.succeed(alice("starah status"))
        assert "claude" in status and "terminal-agent" in status, status
        machine.succeed("id starah-claude && id starah-terminal-agent")

    with subtest("people's approvals are not remembered"):
        policy = machine.succeed("cat /run/current-system/sw/share/polkit-1/actions/org.tulsi.policy")
        apply = policy.split('id="org.tulsi.apply"')[1].split("</action>")[0]
        assert "<allow_active>auth_admin</allow_active>" in apply, apply

    with subtest("Claude Code's install waits for the person in Starah, then is made as starah-claude"):
        machine.succeed(alice("CLAUDECODE=1 tulsi install cowsay >/tmp/install.out 2>&1 &"))
        rid = wait_request("cowsay")
        machine.fail(f"grep -q cowsay {state}")
        machine.succeed(alice(f"starah approve {rid}"))
        machine.wait_until_succeeds(f"grep -q cowsay {state}", timeout=60)
        machine.wait_until_succeeds("git -C /etc/nixos log -1 --format=%B | grep -q 'Tulsi-By: starah-claude'", timeout=30)
        out = machine.succeed("cat /tmp/install.out")
        assert 'Starah agent "claude"' in out, out

    with subtest("rejected in Starah, nothing changes"):
        machine.succeed(alice("(CLAUDECODE=1 tulsi remove cowsay >/tmp/remove.out 2>&1; echo $? >/tmp/remove.rc) >/dev/null 2>&1 &"))
        rid = wait_request("cowsay")
        machine.succeed(alice(f"starah reject {rid}"))
        machine.wait_until_succeeds("test -s /tmp/remove.rc", timeout=60)
        assert machine.succeed("cat /tmp/remove.rc").strip() != "0"
        machine.succeed("grep -q NotAuthorized /tmp/remove.out")
        machine.succeed(f"grep -q cowsay {state}")

    with subtest("an unknown agent runs as the fallback; a config file is passed through"):
        machine.succeed(alice("starah set terminal-agent 3"))
        machine.succeed("printf '%s\\n' '{ pkgs, ... }:' '{' '  environment.systemPackages = [ pkgs.hello ];' '}' > /tmp/c.nix && chmod a+r /tmp/c.nix")
        out = machine.succeed(alice('AGENT=newbot tulsi config apply /tmp/c.nix --summary "hello" 2>&1'))
        assert 'Starah agent "terminal-agent"' in out, out
        machine.succeed("grep -q pkgs.hello /etc/nixos/configuration.nix")
        machine.succeed("git -C /etc/nixos log -1 --format=%B | grep -q 'Tulsi-By: starah-terminal-agent'")

    with subtest("dry runs and reading stay the person's"):
        out = machine.succeed(alice("CLAUDECODE=1 tulsi -n install hello 2>&1"))
        assert "Starah" not in out, out

    with subtest("`claude` in a terminal starts as starah-claude, in the project folder only"):
        machine.succeed(alice("mkdir -p ~/proj ~/private"))
        out = machine.succeed(alice("/etc/agent-test/claude.sh"))
        machine.log(out)
        assert "starah-claude" in out and "/home/alice/proj" in out, out
        assert "HOME=/var/lib/starah-agents/claude/home/alice" in out, out
        assert "/etc/tulsi/agents/skills" in out, out  # TulsiOS' skills, in its own home
        assert "private" not in out, out
        assert machine.succeed("stat -c %U /home/alice/proj/made-by-claude").strip() == "alice"

    with subtest("tulsi-mcp started by Claude Code serves as starah-claude"):
        out = machine.succeed(alice("/etc/agent-test/mcp.sh 2>/tmp/mcp.err"))
        assert "serverInfo" in out, out
        machine.succeed('grep -q "serving as Starah agent \\"claude\\"" /tmp/mcp.err')
  '';
}
