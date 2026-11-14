# The Ocimum Assistant end to end in X11, with a scripted model (no network):
# the conversation drives real tulsi-mcp tool calls against a real tulsid.
# tulsi-mcp runs as the Starah agent `assistant` (level 1, Propose): the change
# waits as a Starah request until the human approves it.
{ self }:
let
  script = [
    {
      text = "Let me find the right package.";
      tool_calls = [
        {
          name = "search_packages";
          input.query = "cow";
        }
      ];
    }
    {
      text = "I'll install **cowsay** for you; please approve the change.";
      tool_calls = [
        {
          name = "apply_change";
          input = {
            operations = [
              {
                op = "addPackage";
                name = "cowsay";
              }
            ];
            reason = "The user asked for cowsay.";
          };
        }
      ];
    }
    { text = "Done: `cowsay` is installed. You can undo it in the Software Center."; }
  ];
in
{
  name = "assistant";

  nodes.machine =
    { pkgs, modulesPath, ... }:
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/x11.nix")
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      test-support.displayManager.auto.user = "alice";
      users.users.alice.extraGroups = [ "wheel" ];
      virtualisation.memorySize = 2048;

      tulsi.state = {
        enable = true;
        file = ./state-test.json;
      };
      tulsi.daemon = {
        enable = true;
        wheelNoPassword = true;
        packageIndex = ./index-test.json;
        rebuildCommand = [ "${pkgs.coreutils}/bin/true" ];
      };
      ocimum.assistant.enable = true;
      services.starah = {
        enable = true;
        session.enable = false;
      };
      # `su` shells are not active local sessions: let wheel answer Starah here.
      security.polkit.extraConfig = ''
        polkit.addRule(function(action, subject) {
          if (action.id.indexOf("org.starah.") == 0 && subject.isInGroup("wheel")) {
            return polkit.Result.YES;
          }
        });
      '';

      environment.systemPackages = [
        pkgs.git
        pkgs.glib.bin # gdbus
        pkgs.jq
      ];
      environment.etc."assistant/script.json".text = builtins.toJSON script;
      # An agent trying to accept an unfree licence itself (tulsid must refuse).
      environment.etc."assistant/accept-licence".source = pkgs.writeShellScript "accept-licence" ''
        exec ${pkgs.systemd}/bin/busctl call org.tulsi.Manager1 /org/tulsi/Manager1           org.tulsi.Manager1 Apply s           '[{"op":"acceptLicense","name":"claude-code"},{"op":"addPackage","name":"claude-code"}]'
      '';
    };

  testScript = ''
    import json
    from datetime import timedelta

    machine.wait_for_x()
    machine.wait_for_unit("tulsid.service")
    machine.wait_until_succeeds("pgrep -u alice -o icewm", timeout=timedelta(minutes=5))
    wm = machine.succeed("pgrep -u alice -o icewm").strip()
    session = dict(
        line.split("=", 1)
        for line in machine.succeed(f"tr '\\0' '\\n' < /proc/{wm}/environ").splitlines()
        if "=" in line
    )
    env = " ".join(
        f"{k}={session[k]}"
        for k in ["DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS"]
        if k in session
    )
    env += (
        " OCIMUM_ASSISTANT_PROVIDER=fake:/etc/assistant/script.json"
        " OCIMUM_ASSISTANT_FAKE_LOG=/tmp/fake-model.jsonl"
        " OCIMUM_ASSISTANT_MCP=\"starah run --agent assistant -- tulsi-mcp --approval starah\""
    )

    def alice(cmd):
        return f"su - alice -c '{env} {cmd}'"

    with subtest("the assistant opens"):
        machine.succeed(alice("ocimum-assistant >/tmp/assistant.log 2>&1 &"))
        machine.wait_until_succeeds(
            alice("xwininfo -root -tree") + " | grep -qF '\"Assistant\"'", timeout=timedelta(minutes=2)
        )
        machine.sleep(2)
        machine.screenshot("assistant-start")

    with subtest("a plain-language request becomes a Starah request, then an approved change"):
        machine.succeed(alice(
            "gdbus call --session --dest org.tulsi.Assistant --object-path /org/tulsi/Assistant "
            "--method org.gtk.Actions.Activate ask \"[<\\\"install cowsay please\\\">]\" \"{}\""
        ))
        machine.wait_until_succeeds("starah requests | grep -q assistant", timeout=timedelta(minutes=2))
        pending = json.loads(machine.succeed(
            "busctl --json=short call org.starah.Broker1 /org/starah/Broker1 org.starah.Broker1 Requests"
            " | jq -r .data[0]"
        ))
        assert len(pending) == 1, pending
        approval = pending[0]
        assert approval["agent"] == "assistant" and approval["action"] == "org.tulsi.apply", approval
        assert approval["description"]["changes"] == ["+ package cowsay"], approval
        assert approval["description"]["reason"] == "The user asked for cowsay.", approval
        # tulsi-mcp runs as the Starah agent, sandboxed, not as alice.
        machine.succeed("pgrep -u starah-assistant -x tulsi-mcp")
        machine.fail("pgrep -u alice -x tulsi-mcp")
        # Nothing happens before the human answers.
        machine.sleep(2)
        machine.fail("grep -q cowsay /etc/nixos/tulsi/state.json")
        machine.succeed(alice(f"starah approve {approval['id']}"))
        machine.wait_until_succeeds("grep -q cowsay /etc/nixos/tulsi/state.json", timeout=timedelta(minutes=2))
        machine.wait_until_succeeds("test $(wc -l < /tmp/fake-model.jsonl) -ge 3", timeout=timedelta(minutes=1))
        machine.sleep(2)
        machine.screenshot("assistant-done")

    with subtest("the model saw the real tool results"):
        requests = [json.loads(l) for l in machine.succeed("cat /tmp/fake-model.jsonl").splitlines()]
        assert requests[0]["messages"][0]["content"] == "install cowsay please", requests[0]
        search_result = requests[1]["messages"][-1]["content"][0]
        assert search_result["type"] == "tool_result" and "cowsay" in search_result["content"], search_result
        apply_result = requests[2]["messages"][-1]["content"][0]
        assert "Applied and rebuilt" in apply_result["content"], apply_result
        machine.succeed("git -C /etc/nixos log -1 --format=%s | grep -qx 'tulsi: install cowsay'")

    with subtest("an agent cannot accept a software licence"):
        out = machine.fail("starah run --agent assistant -- /etc/assistant/accept-licence 2>&1")
        assert "cannot accept a software licence" in out, out
        machine.fail("grep -q claude-code /etc/nixos/tulsi/state.json")

    with subtest("Starah audited the request, the decision and tulsid's check"):
        audit = machine.succeed("starah audit 100")
        assert '"event":"ask"' in audit and '"event":"decide"' in audit, audit
        assert '"action":"org.tulsi.apply"' in audit and '"outcome":"allow"' in audit, audit

    machine.succeed("cat /tmp/assistant.log >&2")
  '';
}
