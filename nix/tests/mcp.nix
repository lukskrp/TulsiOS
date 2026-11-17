# tulsi-mcp against a real tulsid (fake rebuild): MCP sessions are replayed
# from JSON-lines fixtures; approval comes from stand-in programs, and once
# from the real ocimum-approve dialog in an X session.
{ self }:
let
  init = {
    jsonrpc = "2.0";
    id = 1;
    method = "initialize";
    params = {
      protocolVersion = "2025-06-18";
      capabilities = { };
      clientInfo = {
        name = "nixos-test";
        version = "1";
      };
    };
  };
  call = id: name: arguments: {
    jsonrpc = "2.0";
    inherit id;
    method = "tools/call";
    params = { inherit name arguments; };
  };
  session = calls: builtins.concatStringsSep "\n" (map builtins.toJSON ([ init ] ++ calls)) + "\n";
  reason = "the user asked for it";
  goodConfig = ''
    { config, lib, pkgs, ... }:
    {
      services.printing.enable = true;
    }
  '';
in
{
  name = "mcp";

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

      tulsi.state = {
        enable = true;
        file = ./state-test.json;
      };
      tulsi.daemon = {
        enable = true;
        wheelNoPassword = true;
        packageIndex = ./index-test.json;
        rebuildCommand = [
          "${pkgs.writeShellScript "fake-rebuild" ''
            echo "building the system configuration..."
            if grep -q brokenOption configuration.nix 2>/dev/null; then
              echo "error: The option 'brokenOption' does not exist." >&2
              exit 1
            fi
          ''}"
        ];
      };
      ocimum.softwareCenter.enable = true; # provides ocimum-approve
      environment.systemPackages = [ pkgs.git ];

      environment.etc = {
        "mcp/approve".source = pkgs.writeShellScript "approve" "cat > /tmp/approval-request.json; exit 0";
        "mcp/deny".source = pkgs.writeShellScript "deny" "cat > /dev/null; exit 1";
        "mcp/read.jsonl".text = session [
          (call 2 "search_packages" { query = "cow"; })
          (call 3 "plan_change" {
            operations = [
              {
                op = "addPackage";
                name = "sl";
              }
            ];
          })
          (call 4 "get_state" { })
          {
            jsonrpc = "2.0";
            id = 5;
            method = "tools/list";
          }
        ];
        "mcp/install-cowsay.jsonl".text = session [
          (call 2 "apply_change" {
            operations = [
              {
                op = "addPackage";
                name = "cowsay";
              }
            ];
            inherit reason;
          })
        ];
        "mcp/install-sl.jsonl".text = session [
          (call 2 "apply_change" {
            operations = [
              {
                op = "addPackage";
                name = "sl";
              }
            ];
            inherit reason;
          })
        ];
        "mcp/install-typo.jsonl".text = session [
          (call 2 "apply_change" {
            operations = [
              {
                op = "addPackage";
                name = "cowsy";
              }
            ];
            inherit reason;
          })
        ];
        "mcp/bad-syntax.jsonl".text = session [
          (call 2 "propose_configuration_edit" { contents = "{ services.printing.enable = true;"; })
        ];
        "mcp/edit-config.jsonl".text = session [
          (call 2 "propose_configuration_edit" { contents = goodConfig; })
          (call 3 "apply_configuration_edit" {
            contents = goodConfig;
            summary = "enable printing";
            inherit reason;
          })
          (call 4 "read_configuration" { })
        ];
        "mcp/broken-config.jsonl".text = session [
          (call 2 "apply_configuration_edit" {
            contents = "{ ... }: { brokenOption = true; }\n";
            summary = "set a nonexistent option";
            inherit reason;
          })
        ];
        "mcp/undo.jsonl".text = session [ (call 2 "undo_last_change" { inherit reason; }) ];
      };
    };

  testScript = ''
    import json
    from datetime import timedelta

    config = "/etc/nixos/configuration.nix"
    state = "/etc/nixos/tulsi/state.json"

    def mcp(fixture, approver="/etc/mcp/approve"):
        """Runs one MCP session as alice; returns responses by id."""
        out = machine.succeed(
            f"su - alice -c 'tulsi-mcp --approver {approver} < /etc/mcp/{fixture}.jsonl'"
        )
        msgs = [json.loads(line) for line in out.splitlines() if line.strip()]
        return {m["id"]: m for m in msgs if "id" in m}

    def text(msg):
        return msg["result"]["content"][0]["text"]

    machine.wait_for_x()
    machine.wait_for_unit("tulsid.service")

    with subtest("handshake and read-only tools"):
        r = mcp("read")
        assert r[1]["result"]["serverInfo"]["name"] == "tulsi-mcp", r[1]
        assert "cowsay" in text(r[2]), r[2]
        assert "+ package sl" in text(r[3]), r[3]
        assert "hello" in text(r[4]), r[4]
        tools = {t["name"] for t in r[5]["result"]["tools"]}
        # 10 system tools + 4 packaging tools (ADR 0013).
        assert len(tools) == 14 and {"fetch_source", "build_package", "try_package",
                                     "propose_local_package"} <= tools, sorted(tools)
        machine.fail(f"grep -q '\"sl\"' {state}")

    with subtest("an approved change is applied, with the plan shown to the approver"):
        r = mcp("install-cowsay")
        assert r[2]["result"]["isError"] is False, r[2]
        machine.succeed(f"grep -q cowsay {state}")
        request = json.loads(machine.succeed("cat /tmp/approval-request.json"))
        assert request["changes"] == ["+ package cowsay"], request
        assert request["reason"] == "the user asked for it", request

    with subtest("a denied change is not applied"):
        r = mcp("install-sl", approver="/etc/mcp/deny")
        assert r[2]["result"]["isError"] is True and "rejected" in text(r[2]), r[2]
        machine.fail(f"grep -q '\"sl\"' {state}")

    with subtest("invalid requests are refused before anyone is asked"):
        machine.succeed("rm -f /tmp/approval-request.json")
        r = mcp("install-typo")
        assert "did you mean: cowsay" in text(r[2]), r[2]
        machine.fail("test -e /tmp/approval-request.json")
        r = mcp("bad-syntax")
        assert r[2]["result"]["isError"] is True and "not valid Nix" in text(r[2]), r[2]

    with subtest("configuration.nix edits: diff, approval, apply, history"):
        r = mcp("edit-config")
        assert "+  services.printing.enable = true;" in text(r[2]), r[2]
        assert r[3]["result"]["isError"] is False, r[3]
        machine.succeed(f"grep -q 'services.printing.enable = true' {config}")
        assert "services.printing.enable" in text(r[4]), r[4]
        request = json.loads(machine.succeed("cat /tmp/approval-request.json"))
        assert "+  services.printing.enable = true;" in request["diff"], request
        machine.succeed(
            "git -C /etc/nixos log -1 --format=%s | grep -qx 'tulsi: edit configuration.nix: enable printing'"
        )

    with subtest("a configuration edit whose rebuild fails is rolled back"):
        r = mcp("broken-config")
        assert r[2]["result"]["isError"] is True and "rolled back" in text(r[2]), r[2]
        machine.fail(f"grep -q brokenOption {config}")
        machine.succeed(f"grep -q 'services.printing.enable = true' {config}")

    with subtest("undo reverts the configuration edit"):
        r = mcp("undo")
        assert r[2]["result"]["isError"] is False, r[2]
        machine.fail(f"test -e {config}")
        machine.succeed("git -C /etc/nixos log -1 --format=%s | grep -q 'undo edit configuration.nix'")

    with subtest("the desktop dialog asks, and Enter means Reject"):
        machine.wait_until_succeeds("pgrep -u alice -o icewm", timeout=timedelta(minutes=5))
        wm = machine.succeed("pgrep -u alice -o icewm").strip()
        session = dict(
            line.split("=", 1)
            for line in machine.succeed(f"tr '\\0' '\\n' < /proc/{wm}/environ").splitlines()
            if "=" in line
        )
        env = " ".join(f"{k}={session[k]}" for k in ["DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR"] if k in session)
        machine.succeed(
            f"su - alice -c '{env} tulsi-mcp < /etc/mcp/install-sl.jsonl > /tmp/gui.jsonl 2>/tmp/gui.err &'"
        )
        machine.wait_until_succeeds(
            f"su - alice -c '{env} xwininfo -root -tree' | grep -qF 'Approve System Change'",
            timeout=timedelta(minutes=2),
        )
        machine.sleep(2)
        machine.screenshot("approval-dialog")
        machine.send_key("ret")
        machine.wait_until_succeeds("test $(grep -c . /tmp/gui.jsonl) -ge 2", timeout=timedelta(minutes=1))
        r = {m["id"]: m for m in map(json.loads, machine.succeed("cat /tmp/gui.jsonl").splitlines())}
        assert r[2]["result"]["isError"] is True and "rejected" in text(r[2]), r[2]
        machine.fail(f"grep -q '\"sl\"' {state}")
  '';
}
